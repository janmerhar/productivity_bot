import asyncio
import re
from typing import Any, Dict, List, Mapping, Optional

import discord
from discord.ext import commands

from classes.DailyJob import CronSchedule, DailyJob
from classes.DailyJobManager import DailyJobManager
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.cron_schedule import CronConversionError, resolve_cron_expression
from services.discord_helpers import resolve_messageable_channel
from services.error_reporting import ValidationError, handle_interaction_error

_MODAL_SELECTS_SUPPORTED = True


def _schedule_expression(schedule: Optional[Mapping[str, Any]]) -> str:
    if not isinstance(schedule, Mapping):
        return ""
    return str(schedule.get("expression") or "").strip()


def _parse_channel_id(value: str) -> int:
    cleaned = value.strip()
    mention_match = re.fullmatch(r"<#(\d+)>", cleaned)
    if mention_match is not None:
        return int(mention_match.group(1))
    if cleaned.isdigit():
        return int(cleaned)
    raise ValidationError(
        "Please provide a valid channel mention or channel id.",
        ephemeral=True,
    )


def _header_value(job: DailyJob) -> str:
    return str((job.data or {}).get("header") or "").strip()


def _payload_input_for_job(job: DailyJob) -> str:
    if job.type == "message":
        return str((job.data or {}).get("message") or "").strip()
    if job.type == "crypto":
        tickers = (job.data or {}).get("tickers") or []
        if isinstance(tickers, list) and tickers:
            return str(tickers[0]).strip().lower()
        return ""
    if job.type == "stock":
        return str((job.data or {}).get("ticker") or "").strip().upper()
    return ""


def _payload_label_for_job_type(job_type: str) -> str:
    if job_type == "message":
        return "Message"
    if job_type == "crypto":
        return "Crypto ticker (CoinGecko id)"
    if job_type == "stock":
        return "Stock ticker"
    return "Payload"


def _build_job_payload(job_type: str, value: str, header: str) -> Dict[str, Any]:
    cleaned = value.strip()
    if not cleaned:
        raise ValidationError("Payload value cannot be empty.", ephemeral=True)

    if job_type == "message":
        payload: Dict[str, Any] = {"message": cleaned}
    elif job_type == "crypto":
        payload = {"tickers": [cleaned.lower()]}
    elif job_type == "stock":
        payload = {"ticker": cleaned.upper()}
    else:
        raise ValidationError("Editing is not supported for this job type.", ephemeral=True)

    header_value = header.strip()
    if header_value:
        payload["header"] = header_value
    return payload


def _build_channel_select_options(
    interaction: discord.Interaction,
    current_channel_id: Optional[int],
) -> List[discord.SelectOption]:
    guild = interaction.guild
    if guild is None:
        return []

    options: List[discord.SelectOption] = []
    for channel in guild.text_channels:
        permissions = channel.permissions_for(interaction.user)
        if not permissions.view_channel or not permissions.send_messages:
            continue

        options.append(
            discord.SelectOption(
                label=f"#{channel.name}"[:100],
                value=str(channel.id),
                default=(current_channel_id is not None and channel.id == current_channel_id),
            )
        )
        if len(options) >= 25:
            break

    return options


class ScheduledJobEditModal(discord.ui.Modal):
    def __init__(
        self,
        view: "ScheduledJobActionView",
        job: DailyJob,
        source_message: Optional[discord.Message] = None,
    ) -> None:
        super().__init__(title=f"Edit {job.type.capitalize()} Job")
        self._view = view
        self._job_type = job.type
        self._source_message = source_message

        self.schedule = discord.ui.TextInput(
            label="Schedule",
            placeholder="Cron expression or natural language schedule",
            required=True,
            max_length=120,
            default=_schedule_expression(job.schedule),
        )
        self.payload_value = discord.ui.TextInput(
            label=_payload_label_for_job_type(job.type),
            placeholder="Updated payload value",
            required=True,
            max_length=400,
            default=_payload_input_for_job(job),
        )
        self.header = discord.ui.TextInput(
            label="Header (optional)",
            placeholder="Optional message shown above embeds",
            required=False,
            max_length=200,
            default=_header_value(job),
        )
        self.add_item(self.schedule)
        self.add_item(self.payload_value)
        self.add_item(self.header)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        raw_schedule = str(self.schedule.value or "").strip()
        raw_payload = str(self.payload_value.value or "")
        raw_header = str(self.header.value or "")
        try:
            cron_expression = await asyncio.to_thread(
                resolve_cron_expression,
                raw_schedule,
            )
        except CronConversionError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(str(exc), ephemeral=True, cause=exc),
            )
            return

        try:
            payload = _build_job_payload(self._job_type, raw_payload, raw_header)
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)
            return

        manager = DailyJobManager()
        try:
            updated = await asyncio.to_thread(
                manager.update_job,
                self._view.job_id,
                data=payload,
                schedule=CronSchedule(expression=cron_expression),
                channel_id=self._view.channel_id,
                guild_id=self._view.guild_id,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)
            return

        if not updated:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=True,
                ),
                ephemeral=True,
            )
            return

        refreshed_payload = DailyTaskEmbeds.job_details_embed(
            job_id=self._view.job_id,
            job_type=self._job_type,
            channel_id=self._view.channel_id,
            schedule_text=raw_schedule,
            cron_expression=cron_expression,
            payload=payload,
            description="Scheduled job updated.",
            ok=True,
        )
        candidates = [self._source_message, interaction.message, getattr(self._view, "message", None)]
        refreshed = False
        for candidate in candidates:
            if candidate is None:
                continue
            try:
                await candidate.edit(view=self._view, **refreshed_payload)
                refreshed = True
                break
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        if not refreshed:
            await interaction.followup.send(
                "Updated the job, but I couldn't refresh the job card message.",
                ephemeral=True,
            )


class ScheduledJobChangeChannelModal(discord.ui.Modal, title="Change Job Channel"):
    def __init__(
        self,
        view: "ScheduledJobActionView",
        channel_options: Optional[List[discord.SelectOption]] = None,
    ) -> None:
        super().__init__()
        self._view = view
        self.channel_select: Optional[discord.ui.Select] = None
        self.channel_select_label: Optional[discord.ui.Label] = None
        self.channel_input: Optional[discord.ui.TextInput] = None

        if channel_options:
            try:
                self.channel_select = discord.ui.Select(
                    placeholder="Choose a channel",
                    min_values=1,
                    max_values=1,
                    options=channel_options[:25],
                )
                self.channel_select_label = discord.ui.Label(
                    text="Destination channel",
                    component=self.channel_select,
                )
                self.add_item(self.channel_select_label)
            except Exception:
                self.channel_select = None
                self.channel_select_label = None

        if self.channel_select is None:
            self.channel_input = discord.ui.TextInput(
                label="Destination channel",
                placeholder="Use a channel mention (e.g. #general) or channel id",
                required=True,
                max_length=64,
            )
            if view.channel_id:
                self.channel_input.default = f"<#{view.channel_id}>"
            self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            if self.channel_select is not None:
                raw_value = (
                    self.channel_select.values[0]
                    if self.channel_select.values
                    else ""
                )
                new_channel_id = int(raw_value)
            else:
                raw_input = (
                    str(self.channel_input.value or "")
                    if self.channel_input is not None
                    else ""
                )
                new_channel_id = _parse_channel_id(raw_input)
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)
            return

        bot = interaction.client
        if not isinstance(bot, commands.Bot):
            await handle_interaction_error(
                interaction,
                ValidationError("Bot is not ready to change this job.", ephemeral=True),
                ephemeral=True,
            )
            return

        resolved_channel = await resolve_messageable_channel(bot, new_channel_id)
        if resolved_channel is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "I can't access that destination channel.",
                    ephemeral=True,
                ),
                ephemeral=True,
            )
            return

        if self._view.guild_id is not None:
            channel_guild = getattr(resolved_channel, "guild", None)
            if channel_guild is None or channel_guild.id != self._view.guild_id:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Please choose a channel from the same server as this job.",
                        ephemeral=True,
                    ),
                    ephemeral=True,
                )
                return

        manager = DailyJobManager()
        try:
            updated = await asyncio.to_thread(
                manager.update_job,
                self._view.job_id,
                new_channel_id=new_channel_id,
                channel_id=self._view.channel_id,
                guild_id=self._view.guild_id,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)
            return

        if not updated:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=True,
                ),
                ephemeral=True,
            )
            return

        self._view.channel_id = new_channel_id
        await interaction.followup.send(
            f"Updated job `{self._view.job_id}` to post in <#{new_channel_id}>.",
            ephemeral=True,
        )


class ScheduledJobActionView(discord.ui.View):
    def __init__(
        self,
        *,
        job_id: str,
        channel_id: Optional[int],
        guild_id: Optional[int],
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.job_id = str(job_id)
        self.channel_id = channel_id
        self.guild_id = guild_id

    async def _load_job(self, manager: DailyJobManager) -> Optional[DailyJob]:
        return await asyncio.to_thread(
            manager.get_job,
            self.job_id,
            self.channel_id,
            self.guild_id,
        )

    @discord.ui.button(label="Run now", style=discord.ButtonStyle.success)
    async def run_now(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        manager = DailyJobManager()
        try:
            job = await self._load_job(manager)
            if job is None:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=True,
                )

            if job.type not in {"message", "crypto", "stock"}:
                raise ValidationError(
                    "Run now is currently supported for message, crypto, and stock jobs.",
                    ephemeral=True,
                )

            payload = await asyncio.to_thread(job.run)
            if not payload:
                raise ValidationError(
                    "This job did not produce any output to send.",
                    ephemeral=True,
                )

            bot = interaction.client
            if not isinstance(bot, commands.Bot):
                raise ValidationError("Bot is not ready to send this job.", ephemeral=True)

            channel = await resolve_messageable_channel(bot, job.channel_id)
            if channel is None:
                raise ValidationError(
                    "I can't access the destination channel for this job.",
                    ephemeral=True,
                )

            await channel.send(**payload)
            await interaction.followup.send(
                f"Ran job `{self.job_id}` now in <#{job.channel_id}>.",
                ephemeral=True,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)

    @discord.ui.button(label="Edit", style=discord.ButtonStyle.secondary)
    async def edit(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        manager = DailyJobManager()
        try:
            job = await self._load_job(manager)
            if job is None:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=True,
                )
            if job.type not in {"message", "crypto", "stock"}:
                raise ValidationError(
                    "Editing is currently supported for message, crypto, and stock jobs.",
                    ephemeral=True,
                )
            await interaction.response.send_modal(
                ScheduledJobEditModal(
                    self,
                    job,
                    source_message=interaction.message,
                )
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)

    @discord.ui.button(label="Change Channel", style=discord.ButtonStyle.primary)
    async def change_channel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        global _MODAL_SELECTS_SUPPORTED
        try:
            manager = DailyJobManager()
            job = await self._load_job(manager)
            if job is None:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=True,
                )

            channel_options = _build_channel_select_options(interaction, self.channel_id)
            if _MODAL_SELECTS_SUPPORTED:
                try:
                    await interaction.response.send_modal(
                        ScheduledJobChangeChannelModal(
                            self,
                            channel_options=channel_options,
                        )
                    )
                    return
                except discord.HTTPException as exc:
                    if exc.code == 50035 and "must be one of (4,)" in str(exc):
                        _MODAL_SELECTS_SUPPORTED = False
                    else:
                        raise

            await interaction.response.send_modal(ScheduledJobChangeChannelModal(self))
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        manager = DailyJobManager()
        try:
            deleted = await asyncio.to_thread(
                manager.delete_job,
                self.job_id,
                self.channel_id,
                self.guild_id,
            )
            if not deleted:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=True,
                )

            for child in self.children:
                child.disabled = True

            if interaction.message is not None:
                await interaction.message.edit(view=self)

            await interaction.followup.send(
                f"Deleted job `{self.job_id}`.",
                ephemeral=True,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)
