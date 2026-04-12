import asyncio
from typing import List, Optional

import discord
from discord.ext import commands

from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from services.cron_schedule import is_valid_cron_expression
from services.discord_helpers import (
    resolve_messageable_channel,
)
from services.error_reporting import ValidationError, handle_interaction_error
from services.reminder_destination import (
    build_reminder_destination_select_options,
    parse_reminder_destination_value,
)
from services.timezone_gate import ensure_user_timezone
from views.ReminderOutputView import ReminderOutputView


def _clamp_text(value: Optional[str], limit: int = 4000) -> str:
    return str(value or "")[:limit]


def _build_destination_select_options(
    guild: Optional[discord.Guild],
    current_channel_id: Optional[int],
    *,
    is_private_selected: bool = False,
) -> List[discord.SelectOption]:
    return build_reminder_destination_select_options(
        guild,
        current_channel_id,
        is_private_selected=is_private_selected,
    )


def _parse_destination_value(value: str):
    return parse_reminder_destination_value(value)


class ReminderEditModal(discord.ui.Modal, title="Edit Reminder"):
    def __init__(
        self,
        job: DailyJob,
        channel_options: Optional[List[discord.SelectOption]] = None,
        *,
        parent_view: Optional["discord.ui.View"] = None,
        source_message: Optional[discord.Message] = None,
        response_ephemeral: bool = False,
    ) -> None:
        super().__init__()
        self._parent_view = parent_view
        self._source_message = source_message
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
            label="Reminder",
            placeholder="Updated reminder value",
            required=True,
            max_length=400,
            style=discord.TextStyle.short,
            default=_clamp_text(values.get("reminder"), 400),
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
                placeholder="Use `Private`, a channel mention, or a channel id",
                required=True,
                max_length=64,
                default=_clamp_text(values.get("destination_channel"), 64),
            )

        self.add_item(self.schedule)
        self.add_item(self.reminder)
        self.add_item(self.description)
        if self.destination_channel_label is not None:
            self.add_item(self.destination_channel_label)
        elif self.destination_channel_input is not None:
            self.add_item(self.destination_channel_input)

    async def _refresh_parent(
        self,
        interaction: discord.Interaction,
        *,
        result_message: Optional[str] = None,
    ) -> bool:
        refresh_method = getattr(self._parent_view, "refresh_message", None)
        if callable(refresh_method):
            return await refresh_method(
                interaction,
                source_message=self._source_message,
                result_message=result_message,
            )
        return False

    def _should_send_followup_result(self, refreshed_parent: bool) -> bool:
        return not (
            refreshed_parent and isinstance(self._parent_view, ReminderOutputView)
        )

    async def _apply_update(
        self,
        interaction: discord.Interaction,
        *,
        schedule: str,
        reminder: str,
        description: str,
        destination_type: str,
        destination_channel_id: Optional[int],
        timezone: Optional[str],
    ) -> None:
        try:
            updated_job = await asyncio.to_thread(
                ReminderFunctions.update_reminder,
                reminder_id=self._job_id,
                guild_id=self._guild_id,
                schedule=schedule,
                reminder=reminder,
                description=description,
                destination_channel_id=destination_channel_id,
                destination_type=destination_type,
                destination_user_id=interaction.user.id,
                ephemeral=self._response_ephemeral,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
            return

        refreshed_parent = await self._refresh_parent(
            interaction,
            result_message="Reminder updated.",
        )
        if not self._should_send_followup_result(refreshed_parent):
            return

        reminder_view = ReminderOutputView(
            job=updated_job,
            guild=interaction.guild,
            result_message="Reminder updated.",
            ok=True,
            user_id=interaction.user.id,
            response_ephemeral=self._response_ephemeral,
        )
        await interaction.followup.send(
            ephemeral=self._response_ephemeral,
            **reminder_view.response_payload(),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_schedule = str(self.schedule.value or "").strip()
        raw_reminder = str(self.reminder.value or "").strip()
        raw_description = str(self.description.value or "").strip()

        try:
            if self.destination_channel_select is not None:
                raw_value = (
                    self.destination_channel_select.values[0]
                    if self.destination_channel_select.values
                    else ""
                )
                destination_type, destination_channel_id = _parse_destination_value(
                    raw_value
                )
            else:
                raw_destination_channel = str(
                    self.destination_channel_input.value or ""
                ).strip()
                destination_type, destination_channel_id = _parse_destination_value(
                    raw_destination_channel
                )
            bot = interaction.client
            if not isinstance(bot, commands.Bot):
                raise ValidationError("Bot is not ready to update this reminder.")

            if destination_type == "channel":
                resolved_channel = await resolve_messageable_channel(
                    bot,
                    destination_channel_id,
                )
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
                        description=raw_description,
                        destination_type=destination_type,
                        destination_channel_id=destination_channel_id,
                        timezone=resolved_timezone,
                    )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing `/reminder edit`.",
                    response_ephemeral=self._response_ephemeral,
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=self._response_ephemeral)
            await self._apply_update(
                interaction,
                schedule=schedule_to_submit,
                reminder=raw_reminder,
                description=raw_description,
                destination_type=destination_type,
                destination_channel_id=destination_channel_id,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )


class ReminderCreateModal(discord.ui.Modal, title="Create Reminder"):
    def __init__(
        self,
        *,
        parent_view: Optional["discord.ui.View"] = None,
        default_channel_id: Optional[int],
        default_destination_type: str = "channel",
        guild: Optional[discord.Guild] = None,
        source_message: Optional[discord.Message] = None,
        response_ephemeral: bool = False,
        initial_reminder: Optional[str] = None,
        guild_id: Optional[int] = None,
    ) -> None:
        super().__init__()
        self._parent_view = parent_view
        self._default_channel_id = default_channel_id
        self._source_message = source_message
        self._response_ephemeral = bool(response_ephemeral)
        self._guild_id = (
            guild_id if guild_id is not None else getattr(parent_view, "guild_id", None)
        )
        self._guild = guild if guild is not None else getattr(parent_view, "guild", None)
        self._default_destination_type = (
            default_destination_type.strip().lower()
            if default_destination_type
            else "channel"
        )

        self.schedule = discord.ui.TextInput(
            label="Schedule",
            placeholder="Cron expression or natural language schedule",
            required=True,
            max_length=120,
        )
        self.reminder = discord.ui.TextInput(
            label="Reminder",
            placeholder="Reminder name",
            required=True,
            max_length=400,
            style=discord.TextStyle.short,
            default=_clamp_text(initial_reminder, 400),
        )
        self.ping_select = discord.ui.UserSelect(
            placeholder="Choose members to ping",
            min_values=0,
            max_values=25,
            required=False,
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
        )
        self.destination_channel_select: Optional[discord.ui.Select] = None
        self.destination_channel_label: Optional[discord.ui.Label] = None

        channel_options = _build_destination_select_options(
            self._guild,
            self._default_channel_id,
            is_private_selected=self._default_destination_type == "private",
        )
        if channel_options:
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

        self.add_item(self.reminder)
        self.add_item(self.schedule)
        self.add_item(self.ping_select_label)
        self.add_item(self.description)
        if self.destination_channel_label is not None:
            self.add_item(self.destination_channel_label)

    async def _refresh_parent(self, interaction: discord.Interaction) -> bool:
        refresh_method = getattr(self._parent_view, "refresh_message", None)
        if callable(refresh_method):
            return await refresh_method(
                interaction,
                source_message=self._source_message,
                jump_to_last_page=True,
            )
        return False

    async def _apply_create(
        self,
        interaction: discord.Interaction,
        *,
        schedule: str,
        reminder: str,
        ping: str,
        description: str,
        destination_type: str,
        destination_channel_id: Optional[int],
        timezone: Optional[str],
    ) -> None:
        try:
            created_job, confirmation = await asyncio.to_thread(
                ReminderFunctions.create_reminder,
                guild_id=self._guild_id,
                default_channel_id=self._default_channel_id,
                reminder=reminder,
                schedule=schedule,
                ping_text=ping,
                description=description,
                destination_channel_id=destination_channel_id,
                destination_type=destination_type,
                destination_user_id=interaction.user.id,
                ephemeral=self._response_ephemeral,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
            return

        await self._refresh_parent(interaction)
        reminder_view = ReminderOutputView(
            job=created_job,
            guild=interaction.guild,
            result_message=confirmation,
            ok=True,
            user_id=interaction.user.id,
            response_ephemeral=self._response_ephemeral,
        )
        await interaction.followup.send(
            ephemeral=self._response_ephemeral,
            **reminder_view.response_payload(),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw_schedule = str(self.schedule.value or "").strip()
        raw_reminder = str(self.reminder.value or "").strip()
        raw_description = str(self.description.value or "").strip()

        try:
            if self.destination_channel_select is not None:
                raw_destination = (
                    self.destination_channel_select.values[0]
                    if self.destination_channel_select.values
                    else ""
                )
                destination_type, destination_channel_id = _parse_destination_value(
                    raw_destination
                )
            else:
                destination_type = self._default_destination_type
                destination_channel_id = (
                    None
                    if destination_type == "private"
                    else self._default_channel_id
                )

            if destination_type == "channel" and destination_channel_id is None:
                raise ValidationError("Please choose a destination channel.")

            bot = interaction.client
            if not isinstance(bot, commands.Bot):
                raise ValidationError("Bot is not ready to create this reminder.")

            if destination_type == "channel":
                resolved_channel = await resolve_messageable_channel(
                    bot,
                    destination_channel_id,
                )
                if resolved_channel is None:
                    raise ValidationError("I can't access that destination channel.")

                if self._guild_id is not None:
                    channel_guild = getattr(resolved_channel, "guild", None)
                    if channel_guild is None or channel_guild.id != self._guild_id:
                        raise ValidationError(
                            "Please choose a channel from the same server as this reminder."
                        )

            timezone = None
            if not is_valid_cron_expression(raw_schedule):

                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    await self._apply_create(
                        followup_interaction,
                        schedule=raw_schedule,
                        reminder=raw_reminder,
                        ping=raw_ping,
                        description=raw_description,
                        destination_type=destination_type,
                        destination_channel_id=destination_channel_id,
                        timezone=resolved_timezone,
                    )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing reminder creation.",
                    response_ephemeral=self._response_ephemeral,
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=self._response_ephemeral)
            await self._apply_create(
                interaction,
                schedule=raw_schedule,
                reminder=raw_reminder,
                ping=raw_ping,
                description=raw_description,
                destination_type=destination_type,
                destination_channel_id=destination_channel_id,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )


class ReminderPingModal(discord.ui.Modal, title="Add Ping Users"):
    def __init__(
        self,
        *,
        guild: Optional[discord.Guild],
        guild_id: Optional[int],
        default_channel_id: Optional[int],
        reminder: Optional[str] = None,
        schedule: Optional[str] = None,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        until: Optional[str] = None,
        destination_type: Optional[str] = None,
        destination_channel_id: Optional[int] = None,
        response_ephemeral: bool,
        user_id: int,
        job: Optional[DailyJob] = None,
        parent_view: Optional["discord.ui.View"] = None,
        source_message: Optional[discord.Message] = None,
    ) -> None:
        super().__init__()
        self._guild = guild
        self._job = job
        self._parent_view = parent_view
        self._source_message = source_message
        self._response_ephemeral = bool(response_ephemeral)
        self._user_id = user_id
        self._guild_id = guild_id
        self._default_channel_id = default_channel_id
        self._reminder = str(reminder or "")
        self._schedule = str(schedule or "")
        self._description = description
        self._thumbnail_url = thumbnail_url
        self._until = until
        self._destination_type = (destination_type or "channel").strip().lower()
        self._destination_channel_id = destination_channel_id

        if self._job is not None:
            values = ReminderFunctions.reminder_edit_values(self._job)
            self._guild_id = self._job.guild_id
            if self._default_channel_id is None:
                self._default_channel_id = self._job.channel_id
            self._reminder = str(values.get("reminder") or "")
            self._schedule = ReminderFunctions.schedule_input_for_job(self._job)
            self._description = values.get("description") or None
            self._thumbnail_url = values.get("thumbnail_url") or None
            self._until = values.get("until") or None
            self._destination_type = ReminderFunctions.destination_type(self._job)
            self._destination_channel_id = (
                self._job.channel_id if self._destination_type == "channel" else None
            )

        default_ping_values = [
            discord.Object(id=member_id)
            for member_id in ReminderFunctions.ping_user_ids(self._job)
        ] if self._job is not None else []

        self.ping_select = discord.ui.UserSelect(
            placeholder="Choose users to ping",
            min_values=0,
            max_values=25,
            required=False,
            default_values=default_ping_values[:25],
        )
        self.ping_select_label = discord.ui.Label(
            text="Ping users",
            component=self.ping_select,
        )
        self.add_item(self.ping_select_label)
        self.notify_dm_checkbox = discord.ui.Checkbox(
            custom_id="reminder_ping_notify_dm",
            default=(
                ReminderFunctions.notify_ping_users_in_dm(self._job)
                if self._job is not None
                else False
            ),
        )
        self.notify_dm_label = discord.ui.Label(
            text="Notify also in DMs",
            component=self.notify_dm_checkbox,
        )
        self.add_item(self.notify_dm_label)

    async def _refresh_parent(
        self,
        interaction: discord.Interaction,
        *,
        result_message: Optional[str] = None,
    ) -> bool:
        refresh_method = getattr(self._parent_view, "refresh_message", None)
        if callable(refresh_method):
            return await refresh_method(
                interaction,
                source_message=self._source_message,
                result_message=result_message,
            )
        return False

    def _should_send_followup_result(self, refreshed_parent: bool) -> bool:
        return not (
            refreshed_parent and isinstance(self._parent_view, ReminderOutputView)
        )

    async def _apply_changes(
        self,
        interaction: discord.Interaction,
        *,
        ping: str,
        notify_ping_users_in_dm: bool,
        timezone: Optional[str],
    ) -> None:
        if self._job is not None:
            values = ReminderFunctions.reminder_edit_values(self._job)
            try:
                updated_job = await asyncio.to_thread(
                    ReminderFunctions.update_reminder,
                    reminder_id=str(self._job.id),
                    guild_id=self._guild_id,
                    schedule=self._schedule,
                    reminder=self._reminder,
                    ping_text=ping,
                    description=values.get("description") or None,
                    expires=values.get("expires") or values.get("until") or None,
                    notify_ping_users_in_dm=notify_ping_users_in_dm,
                    destination_channel_id=self._destination_channel_id,
                    destination_type=self._destination_type,
                    destination_user_id=interaction.user.id,
                    ephemeral=self._response_ephemeral,
                    timezone=timezone,
                )
            except Exception as exc:
                await handle_interaction_error(
                    interaction,
                    exc,
                    ephemeral=self._response_ephemeral,
                )
                return

            result_message = "Reminder ping settings updated."
            refreshed_parent = await self._refresh_parent(
                interaction,
                result_message=result_message,
            )
            if not self._should_send_followup_result(refreshed_parent):
                return

            reminder_view = ReminderOutputView(
                job=updated_job,
                guild=interaction.guild or self._guild,
                result_message=result_message,
                ok=True,
                user_id=interaction.user.id,
                response_ephemeral=self._response_ephemeral,
            )
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                **reminder_view.response_payload(),
            )
            return

        try:
            created_job, confirmation = await asyncio.to_thread(
                ReminderFunctions.create_reminder,
                guild_id=self._guild_id,
                default_channel_id=self._default_channel_id,
                reminder=self._reminder,
                schedule=self._schedule,
                ping_text=ping or None,
                thumbnail_url=self._thumbnail_url,
                description=self._description,
                expires=self._until,
                notify_ping_users_in_dm=notify_ping_users_in_dm,
                destination_channel_id=self._destination_channel_id,
                destination_type=self._destination_type,
                destination_user_id=interaction.user.id,
                ephemeral=self._response_ephemeral,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
            return

        reminder_view = ReminderOutputView(
            job=created_job,
            guild=interaction.guild or self._guild,
            result_message=confirmation,
            ok=True,
            user_id=interaction.user.id,
            response_ephemeral=self._response_ephemeral,
        )
        await interaction.followup.send(
            ephemeral=self._response_ephemeral,
            **reminder_view.response_payload(),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "This form is only for the user who started the command.",
                ephemeral=self._response_ephemeral,
            )
            return

        raw_ping = " ".join(
            member.mention
            for member in self.ping_select.values
            if hasattr(member, "mention")
        ).strip()
        notify_ping_users_in_dm = bool(self.notify_dm_checkbox.value)

        try:
            timezone = None
            continue_message = (
                "Timezone saved as `{timezone}`. Continuing reminder ping update."
                if self._job is not None
                else "Timezone saved as `{timezone}`. Continuing `/reminder add`."
            )
            if ReminderFunctions.needs_timezone(
                self._schedule,
                expires=self._until,
            ):

                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    await self._apply_changes(
                        followup_interaction,
                        ping=raw_ping,
                        notify_ping_users_in_dm=notify_ping_users_in_dm,
                        timezone=resolved_timezone,
                    )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message=continue_message,
                    response_ephemeral=self._response_ephemeral,
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=self._response_ephemeral)
            await self._apply_changes(
                interaction,
                ping=raw_ping,
                notify_ping_users_in_dm=notify_ping_users_in_dm,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
