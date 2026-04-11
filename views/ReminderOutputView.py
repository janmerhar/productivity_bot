import asyncio
import datetime
from typing import Optional

import discord
from discord.ext import commands

from classes.DailyJobManager import DailyJobManager
from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from services.discord_helpers import (
    format_reminder_mentions,
    resolve_messageable_channel,
)
from services.error_reporting import ValidationError, handle_interaction_error
from services.reminder_destination import (
    build_reminder_destination_select_options,
    parse_reminder_destination_value,
)


class ReminderChangeChannelModal(discord.ui.Modal, title="Change Reminder Channel"):
    def __init__(
        self,
        view: "ReminderOutputView",
        *,
        channel_options: Optional[list[discord.SelectOption]] = None,
    ) -> None:
        super().__init__()
        self._view = view
        self.channel_select: Optional[discord.ui.Select] = None
        self.channel_select_label: Optional[discord.ui.Label] = None
        self.channel_input: Optional[discord.ui.TextInput] = None

        if channel_options:
            try:
                self.channel_select = discord.ui.Select(
                    placeholder="Choose a destination channel",
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
            default_channel = ReminderFunctions.destination_label(self._view.job)
            self.channel_input = discord.ui.TextInput(
                label="Destination channel",
                placeholder="Use `Private`, a channel mention, or a channel id",
                required=True,
                max_length=64,
                default=default_channel[:64],
            )
            self.add_item(self.channel_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=self._view.response_ephemeral)

        try:
            if self.channel_select is not None:
                raw_value = (
                    self.channel_select.values[0] if self.channel_select.values else ""
                )
                destination_type, new_channel_id = parse_reminder_destination_value(raw_value)
            else:
                raw_value = (
                    str(self.channel_input.value or "")
                    if self.channel_input is not None
                    else ""
                )
                destination_type, new_channel_id = parse_reminder_destination_value(raw_value)

            bot = interaction.client
            if not isinstance(bot, commands.Bot):
                raise ValidationError(
                    "Bot is not ready to change this reminder.",
                    ephemeral=self._view.response_ephemeral,
                )

            if destination_type == "channel":
                resolved_channel = await resolve_messageable_channel(bot, new_channel_id)
                if resolved_channel is None:
                    raise ValidationError(
                        "I can't access that destination channel.",
                        ephemeral=self._view.response_ephemeral,
                    )

                if self._view.guild_id is not None:
                    channel_guild = getattr(resolved_channel, "guild", None)
                    if channel_guild is None or channel_guild.id != self._view.guild_id:
                        raise ValidationError(
                            "Please choose a channel from the same server as this reminder.",
                            ephemeral=self._view.response_ephemeral,
                        )

            manager = DailyJobManager()
            updated_data = {
                **(self._view.job.data or {}),
                "destination_type": destination_type,
            }
            if destination_type == "private":
                updated_data["user_id"] = interaction.user.id
            else:
                updated_data.pop("user_id", None)
            updated = await asyncio.to_thread(
                manager.update_job,
                self._view.job_id,
                new_channel_id=new_channel_id,
                data=updated_data,
                guild_id=self._view.guild_id,
            )
            if not updated:
                raise ValidationError(
                    "That reminder is no longer available.",
                    ephemeral=self._view.response_ephemeral,
                )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._view.response_ephemeral,
            )
            return

        destination_label = "Private" if destination_type == "private" else f"<#{new_channel_id}>"
        result_message = f"Updated reminder `{self._view.job_id}` to post in {destination_label}."
        self._view.ok = True
        await self._view.refresh_message(
            interaction,
            source_message=self._view.message or interaction.message,
            result_message=result_message,
        )


class ReminderOutputView(discord.ui.View):
    def __init__(
        self,
        *,
        job: DailyJob,
        guild: Optional[discord.Guild],
        result_message: str,
        ok: bool = True,
        user_id: Optional[int] = None,
        response_ephemeral: bool = False,
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.job: Optional[DailyJob] = job
        self.guild = guild
        self.result_message = result_message
        self.ok = bool(ok)
        self.user_id = user_id
        self.response_ephemeral = bool(response_ephemeral)
        self.message: Optional[discord.Message] = None
        self.job_id = str(job.id)
        self.guild_id = job.guild_id
        self.channel_id = job.channel_id
        self._sync_button_state()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id is None or interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "Only the user who opened this reminder can manage it.",
            ephemeral=self.response_ephemeral,
        )
        return False

    async def refresh_state(self) -> None:
        self.job = await asyncio.to_thread(
            ReminderFunctions.get_reminder,
            self.job_id,
            self.guild_id,
        )
        if self.job is not None:
            self.channel_id = self.job.channel_id
        self._sync_button_state()

    async def refresh_message(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message] = None,
        jump_to_last_page: bool = False,
        result_message: Optional[str] = None,
    ) -> None:
        del jump_to_last_page
        if result_message is not None:
            self.result_message = result_message

        await self.refresh_state()
        target_message = source_message or interaction.message or self.message
        if target_message is None:
            return

        self.message = target_message
        try:
            await target_message.edit(**self.response_payload())
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    def _sync_button_state(self) -> None:
        has_job = self.job is not None
        self.edit_this_reminder.disabled = not has_job
        self.change_channel.disabled = not has_job
        self.toggle_state.disabled = not has_job
        self.delete_reminder.disabled = not has_job

        if not has_job:
            self.toggle_state.label = None
            self.toggle_state.emoji = "🚫"
            self.toggle_state.style = discord.ButtonStyle.secondary
            return

        if ReminderFunctions.is_paused(self.job):
            self.toggle_state.label = None
            self.toggle_state.emoji = "▶️"
            self.toggle_state.style = discord.ButtonStyle.success
        else:
            self.toggle_state.label = None
            self.toggle_state.emoji = "⏸️"
            self.toggle_state.style = discord.ButtonStyle.secondary

    @staticmethod
    def _format_channel(job: Optional[DailyJob], channel_id: Optional[int]) -> str:
        if job is not None:
            return ReminderFunctions.destination_label(job)
        if channel_id is None:
            return "unknown"
        return f"<#{channel_id}>"

    @staticmethod
    def _format_timestamp(raw_value: str) -> Optional[str]:
        text = str(raw_value or "").strip()
        if not text:
            return None
        try:
            scheduled_at = datetime.datetime.fromisoformat(text)
        except ValueError:
            try:
                scheduled_at = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")
            except ValueError:
                scheduled_at = None
        if scheduled_at is None:
            return f"`{text}`"
        return f"<t:{int(scheduled_at.timestamp())}:f> (<t:{int(scheduled_at.timestamp())}:R>)"

    def _schedule_value(self) -> str:
        if self.job is None:
            return "unknown"

        schedule = self.job.schedule
        if isinstance(schedule, dict):
            mode = str(schedule.get("mode") or "").strip().lower()
            raw_datetime = str(schedule.get("datetime") or "").strip()
        else:
            mode = str(getattr(schedule, "mode", "") or "").strip().lower()
            raw_datetime = str(getattr(schedule, "datetime", "") or "").strip()

        schedule_text = str(
            ReminderFunctions.reminder_edit_values(self.job).get("schedule") or ""
        ).strip()
        if mode == "one-time":
            formatted = self._format_timestamp(raw_datetime)
            if formatted:
                return formatted
        return f"`{schedule_text}`" if schedule_text else "unknown"

    def _embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Reminder",
            description=self.result_message,
            color=discord.Colour.green() if self.ok else discord.Colour.red(),
        )

        if self.job is None:
            embed.add_field(name="ID", value=f"`{self.job_id}`", inline=True)
            embed.add_field(name="Status", value="missing", inline=True)
            embed.add_field(
                name="Destination",
                value=self._format_channel(self.job, self.channel_id),
                inline=True,
            )
            embed.add_field(
                name="Details",
                value="This reminder is no longer available.",
                inline=False,
            )
            return embed

        values = ReminderFunctions.reminder_edit_values(self.job)
        embed.add_field(name="ID", value=f"`{self.job_id}`", inline=True)
        embed.add_field(
            name="Destination",
            value=self._format_channel(self.job, self.channel_id),
            inline=True,
        )
        embed.add_field(
            name="Status",
            value="paused" if ReminderFunctions.is_paused(self.job) else "active",
            inline=True,
        )
        embed.add_field(
            name="Schedule",
            value=self._schedule_value(),
            inline=False,
        )
        embed.add_field(
            name="Name",
            value=(values.get("reminder") or "Untitled reminder")[:1024],
            inline=False,
        )

        ping_value = format_reminder_mentions(
            self.guild,
            values.get("ping_text"),
        )
        if ping_value:
            embed.add_field(name="Ping", value=ping_value[:1024], inline=False)

        description_value = str(values.get("description") or "").strip()
        if description_value:
            embed.add_field(
                name="Description",
                value=description_value[:1024],
                inline=False,
            )

        thumbnail_value = str(values.get("thumbnail_url") or "").strip()
        if thumbnail_value:
            embed.add_field(
                name="Thumbnail URL",
                value=thumbnail_value[:1024],
                inline=False,
            )

        expires_value = self._format_timestamp(values.get("until") or "")
        if expires_value:
            embed.add_field(
                name="Until",
                value=expires_value,
                inline=False,
            )

        return embed

    def payload(self) -> dict:
        return {"embed": self._embed()}

    def response_payload(self) -> dict:
        payload = self.payload()
        if self.children:
            payload["view"] = self
        return payload

    @discord.ui.button(
        emoji="➕",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def add_new_reminder(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        from views.ReminderEditModal import (
            ReminderCreateModal,
        )

        self.message = interaction.message
        default_channel_id = self.channel_id or interaction.channel_id
        await interaction.response.send_modal(
            ReminderCreateModal(
                parent_view=self,
                default_channel_id=default_channel_id,
                default_destination_type=(
                    "private"
                    if self.job is not None
                    and ReminderFunctions.is_private_destination(self.job)
                    else "channel"
                ),
                guild=interaction.guild or self.guild,
                source_message=interaction.message,
                response_ephemeral=self.response_ephemeral,
            )
        )

    @discord.ui.button(
        emoji="✏️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def edit_this_reminder(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        from views.ReminderEditModal import (
            ReminderEditModal,
        )

        self.message = interaction.message
        if self.job is None:
            await interaction.response.send_message(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        channel_options = build_reminder_destination_select_options(
            interaction.guild,
            self.job.channel_id,
            is_private_selected=ReminderFunctions.is_private_destination(self.job),
        )
        await interaction.response.send_modal(
            ReminderEditModal(
                self.job,
                channel_options=channel_options,
                parent_view=self,
                source_message=interaction.message,
                response_ephemeral=self.response_ephemeral,
            )
        )

    @discord.ui.button(
        emoji="📣",
        style=discord.ButtonStyle.primary,
        row=0,
    )
    async def change_channel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        if self.job is None:
            await interaction.response.send_message(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        channel_options = build_reminder_destination_select_options(
            interaction.guild,
            self.job.channel_id,
            is_private_selected=ReminderFunctions.is_private_destination(self.job),
        )
        await interaction.response.send_modal(
            ReminderChangeChannelModal(
                self,
                channel_options=channel_options,
            )
        )

    @discord.ui.button(
        emoji="⏸️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def toggle_state(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        if self.job is None:
            await interaction.response.send_message(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        await interaction.response.defer(ephemeral=self.response_ephemeral)

        try:
            if ReminderFunctions.is_paused(self.job):
                result = await asyncio.to_thread(
                    ReminderFunctions.resume_reminder,
                    self.job_id,
                    self.guild_id,
                )
                desired_message = f"Resumed reminder `{self.job_id}`."
                no_change_message = f"Reminder `{self.job_id}` is already active."
            else:
                result = await asyncio.to_thread(
                    ReminderFunctions.pause_reminder,
                    self.job_id,
                    self.guild_id,
                )
                desired_message = f"Paused reminder `{self.job_id}`."
                no_change_message = f"Reminder `{self.job_id}` is already paused."
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That reminder ID is invalid.",
                    ephemeral=self.response_ephemeral,
                    cause=exc,
                ),
                ephemeral=self.response_ephemeral,
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )
            return

        if result == "missing":
            self.result_message = "This reminder is no longer available."
            self.ok = False
            await self.refresh_message(
                interaction,
                source_message=interaction.message,
                result_message=self.result_message,
            )
            return

        result_message = no_change_message if "already_" in result else desired_message
        self.ok = True
        await self.refresh_message(
            interaction,
            source_message=interaction.message,
            result_message=result_message,
        )

    @discord.ui.button(
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def delete_reminder(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        if self.job is None:
            await interaction.response.send_message(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        await interaction.response.defer(ephemeral=self.response_ephemeral)

        try:
            deleted = await asyncio.to_thread(
                ReminderFunctions.delete_reminder,
                self.job_id,
                self.guild_id,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That reminder ID is invalid.",
                    ephemeral=self.response_ephemeral,
                    cause=exc,
                ),
                ephemeral=self.response_ephemeral,
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )
            return

        if not deleted:
            self.job = None
            self.ok = False
            self.result_message = "This reminder is no longer available."
            self._sync_button_state()
            await self.refresh_message(
                interaction,
                source_message=interaction.message,
                result_message=self.result_message,
            )
            await interaction.followup.send(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        self.job = None
        self.ok = True
        self.result_message = f"Deleted reminder `{self.job_id}`."
        self._sync_button_state()
        await self.refresh_message(
            interaction,
            source_message=interaction.message,
            result_message=self.result_message,
        )
