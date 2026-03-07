import asyncio
import re
from typing import List, Optional

import discord
from discord.ext import commands

from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.cron_schedule import is_valid_cron_expression
from services.discord_helpers import resolve_messageable_channel
from services.error_reporting import ValidationError, handle_interaction_error
from services.timezone_gate import ensure_user_timezone


def _clamp_text(value: Optional[str], limit: int = 4000) -> str:
    return str(value or "")[:limit]


def _parse_channel_id(value: str) -> int:
    cleaned = value.strip()
    mention_match = re.fullmatch(r"<#(\d+)>", cleaned)
    if mention_match is not None:
        return int(mention_match.group(1))
    if cleaned.isdigit():
        return int(cleaned)
    raise ValidationError("Please provide a valid channel mention or channel id.")


def _build_text_channel_select_options(
    guild: Optional[discord.Guild],
    current_channel_id: Optional[int],
) -> List[discord.SelectOption]:
    if guild is None:
        return []

    options: List[discord.SelectOption] = []
    for channel in guild.text_channels:
        options.append(
            discord.SelectOption(
                label=f"#{channel.name}"[:100],
                value=str(channel.id),
                default=(
                    current_channel_id is not None and channel.id == current_channel_id
                ),
            )
        )
        if len(options) >= 25:
            break

    return options


class ReminderEditModal(discord.ui.Modal, title="Edit Reminder"):
    def __init__(
        self,
        job: DailyJob,
        channel_options: Optional[List[discord.SelectOption]] = None,
        *,
        response_ephemeral: bool = True,
    ) -> None:
        super().__init__()
        self._job_id = str(job.id)
        self._guild_id = job.guild_id
        self._response_ephemeral = bool(response_ephemeral)
        self._job_type = job.type
        self._original_schedule_display = ReminderFunctions.schedule_input_for_job(job)

        schedule = job.schedule
        if isinstance(schedule, dict):
            self._original_schedule_expression = str(
                schedule.get("expression") or ""
            ).strip()
        else:
            self._original_schedule_expression = str(
                getattr(schedule, "expression", "") or ""
            ).strip()

        values = ReminderFunctions.reminder_edit_values(job)

        self.schedule = discord.ui.TextInput(
            label="Schedule",
            placeholder="Cron expression or natural language schedule",
            required=True,
            max_length=120,
            default=_clamp_text(values.get("schedule"), 120),
        )
        self.reminder = discord.ui.TextInput(
            label="Stock ticker" if job.type == "stock" else "Reminder",
            placeholder="Updated reminder value",
            required=True,
            max_length=400,
            style=discord.TextStyle.short,
            default=_clamp_text(values.get("reminder"), 400),
        )
        selected_ping_ids = []
        for match in re.findall(r"<@!?(\d+)>", values.get("ping_text") or ""):
            try:
                selected_ping_ids.append(int(match))
            except ValueError:
                continue
        default_ping_values = [discord.Object(id=member_id) for member_id in selected_ping_ids[:25]]
        self.ping_select = discord.ui.UserSelect(
            placeholder="Choose members to ping",
            min_values=0,
            max_values=25,
            required=False,
            default_values=default_ping_values,
        )
        self.ping_select_label = discord.ui.Label(
            text="Ping",
            component=self.ping_select,
        )
        self.description = discord.ui.TextInput(
            label="Description",
            placeholder="Leave blank to clear",
            required=False,
            max_length=1000,
            style=discord.TextStyle.paragraph,
            default=_clamp_text(values.get("description"), 1000),
        )
        self.destination_channel_select: Optional[discord.ui.Select] = None
        self.destination_channel_label: Optional[discord.ui.Label] = None
        self.destination_channel_input: Optional[discord.ui.TextInput] = None

        if channel_options:
            try:
                self.destination_channel_select = discord.ui.Select(
                    placeholder="Choose a destination channel",
                    min_values=1,
                    max_values=1,
                    options=channel_options[:25],
                )
                self.destination_channel_label = discord.ui.Label(
                    text="Destination channel",
                    component=self.destination_channel_select,
                )
            except Exception:
                self.destination_channel_select = None
                self.destination_channel_label = None

        if self.destination_channel_select is None:
            self.destination_channel_input = discord.ui.TextInput(
                label="Destination channel",
                placeholder="Use a channel mention like #general or a channel id",
                required=True,
                max_length=64,
                default=_clamp_text(values.get("destination_channel"), 64),
            )

        self.add_item(self.schedule)
        self.add_item(self.reminder)
        self.add_item(self.ping_select_label)
        self.add_item(self.description)
        if self.destination_channel_label is not None:
            self.add_item(self.destination_channel_label)
        elif self.destination_channel_input is not None:
            self.add_item(self.destination_channel_input)

    async def _apply_update(
        self,
        interaction: discord.Interaction,
        *,
        schedule: str,
        reminder: str,
        ping: str,
        description: str,
        destination_channel_id: int,
        timezone: Optional[str],
    ) -> None:
        try:
            updated_job = await asyncio.to_thread(
                ReminderFunctions.update_reminder,
                self._job_id,
                self._guild_id,
                schedule,
                reminder,
                ping,
                description,
                None,
                destination_channel_id,
                self._response_ephemeral,
                timezone,
            )
            edit_values = ReminderFunctions.reminder_edit_values(updated_job)
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
            return

        await interaction.followup.send(
            ephemeral=self._response_ephemeral,
            **DailyTaskEmbeds.reminder_details_embed(
                reminder_id=str(updated_job.id),
                channel_id=updated_job.channel_id,
                schedule_text=edit_values.get("schedule") or schedule,
                reminder=edit_values.get("reminder") or reminder,
                ping=edit_values.get("ping_text") or "",
                description=edit_values.get("description") or "",
                expires_after=edit_values.get("expires_after") or "",
                paused=ReminderFunctions.is_paused(updated_job),
                result_message="Reminder updated.",
                ok=True,
            ),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_schedule = str(self.schedule.value or "").strip()
        raw_reminder = str(self.reminder.value or "").strip()
        raw_ping = " ".join(
            member.mention for member in self.ping_select.values if hasattr(member, "mention")
        )
        raw_description = str(self.description.value or "").strip()

        try:
            if self.destination_channel_select is not None:
                raw_value = (
                    self.destination_channel_select.values[0]
                    if self.destination_channel_select.values
                    else ""
                )
                destination_channel_id = int(raw_value)
            else:
                raw_destination_channel = str(
                    self.destination_channel_input.value or ""
                ).strip()
                destination_channel_id = _parse_channel_id(raw_destination_channel)
            bot = interaction.client
            if not isinstance(bot, commands.Bot):
                raise ValidationError("Bot is not ready to update this reminder.")

            resolved_channel = await resolve_messageable_channel(bot, destination_channel_id)
            if resolved_channel is None:
                raise ValidationError("I can't access that destination channel.")

            if self._guild_id is not None:
                channel_guild = getattr(resolved_channel, "guild", None)
                if channel_guild is None or channel_guild.id != self._guild_id:
                    raise ValidationError(
                        "Please choose a channel from the same server as this reminder."
                    )

            schedule_to_submit = raw_schedule
            if (
                self._original_schedule_expression
                and raw_schedule == self._original_schedule_display
            ):
                schedule_to_submit = self._original_schedule_expression

            timezone = None
            if not is_valid_cron_expression(schedule_to_submit):

                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    await self._apply_update(
                        followup_interaction,
                        schedule=schedule_to_submit,
                        reminder=raw_reminder,
                        ping=raw_ping,
                        description=raw_description,
                        destination_channel_id=destination_channel_id,
                        timezone=resolved_timezone,
                    )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing `/reminder edit`.",
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=self._response_ephemeral)
            await self._apply_update(
                interaction,
                schedule=schedule_to_submit,
                reminder=raw_reminder,
                ping=raw_ping,
                description=raw_description,
                destination_channel_id=destination_channel_id,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
