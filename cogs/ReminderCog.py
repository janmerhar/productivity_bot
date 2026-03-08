import asyncio
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.ReminderFunctions import ReminderFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.channel_visibility import can_view_channel, filter_visible_items
from services.error_reporting import UserVisibleError
from services.error_reporting import ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility
from views.ReminderEditModal import (
    ReminderCreateModal,
    ReminderEditModal,
    _build_text_channel_select_options,
)
from views.ReminderListView import ReminderListView
from views.ReminderOutputView import ReminderOutputView

_REMINDER_LIST_STATUS_CHOICES = [
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="Active", value="active"),
    app_commands.Choice(name="Paused", value="paused"),
]
_REMINDER_LIST_SCOPE_CHOICES = [
    app_commands.Choice(name="All Server Reminders", value="all"),
    app_commands.Choice(name="This Channel", value="current"),
    app_commands.Choice(name="Specific Channel", value="channel"),
]


@app_commands.context_menu(name="Create Reminder")
async def create_reminder_from_message(
    interaction: discord.Interaction,
    message: discord.Message,
) -> None:
    reminder_text = str(message.content or message.clean_content or "").strip()
    if not reminder_text:
        raise ValidationError(
            "That message has no text to prefill the reminder.",
            ephemeral=True,
        )

    default_channel_id = message.channel.id
    await interaction.response.send_modal(
        ReminderCreateModal(
            default_channel_id=default_channel_id,
            source_message=message,
            response_ephemeral=False,
            initial_reminder=reminder_text,
            guild_id=interaction.guild_id,
        )
    )


class ReminderCog(commands.Cog):
    reminder_group = app_commands.Group(
        name="reminder",
        description="Manage reminders",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("ReminderCog cog loaded")

    async def _send_not_implemented(
        self,
        interaction: discord.Interaction,
        command_name: str,
        ephemeral: bool,
    ) -> None:
        await interaction.response.send_message(
            f"`{command_name}` is not implemented yet.",
            ephemeral=ephemeral,
        )

    async def _send_reminder_output(
        self,
        interaction: discord.Interaction,
        *,
        job,
        result_message: str,
        ephemeral: bool,
    ) -> None:
        reminder_view = ReminderOutputView(
            job=job,
            guild=interaction.guild,
            result_message=result_message,
            ok=True,
            user_id=interaction.user.id,
            response_ephemeral=ephemeral,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **reminder_view.response_payload(),
        )

    async def _get_visible_reminder(
        self,
        interaction: discord.Interaction,
        reminder_id: str,
        *,
        ephemeral: bool,
    ):
        try:
            job = await asyncio.to_thread(
                ReminderFunctions.get_reminder,
                reminder_id,
                interaction.guild_id,
            )
        except ValueError as exc:
            raise ValidationError(
                "That reminder ID is invalid.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if job is None or not can_view_channel(
            interaction,
            job.channel_id,
        ):
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        return job

    @reminder_group.command(
        name="add",
        description="Create a one-time or recurring reminder.",
    )
    @app_commands.describe(
        reminder="Reminder title or primary content",
        time="Cron expression or natural language schedule",
        repeat="Repeat interval or custom repeat expression",
        ping="User or role to ping",
        thumbnail_url="Thumbnail URL",
        skip_days="Comma-separated days to skip",
        description="Reminder description",
        expires_after="Expiration time",
        destination_channel="Destination channel",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        visibility=VISIBILITY_CHOICES,
    )
    async def reminder_add(
        self,
        interaction: discord.Interaction,
        reminder: str,
        time: str,
        repeat: Optional[str] = None,
        ping: Optional[discord.Member | discord.Role] = None,
        thumbnail_url: Optional[str] = None,
        skip_days: Optional[str] = None,
        description: Optional[str] = None,
        expires_after: Optional[str] = None,
        destination_channel: Optional[discord.TextChannel] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")

        needs_timezone = ReminderFunctions.needs_timezone(
            time,
            repeat=repeat,
            expires_after=expires_after,
        )

        async def _continue_with_timezone(
            followup_interaction: discord.Interaction,
            resolved_timezone: str,
        ) -> None:
            await self._create_reminder_from_options(
                interaction=followup_interaction,
                reminder=reminder,
                time=time,
                repeat=repeat,
                ping=ping,
                thumbnail_url=thumbnail_url,
                skip_days=skip_days,
                description=description,
                expires_after=expires_after,
                destination_channel=destination_channel,
                ephemeral=ephemeral,
                timezone=resolved_timezone,
            )

        timezone = None
        if needs_timezone:
            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/reminder add`.",
                response_ephemeral=ephemeral,
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._create_reminder_from_options(
            interaction=interaction,
            reminder=reminder,
            time=time,
            repeat=repeat,
            ping=ping,
            thumbnail_url=thumbnail_url,
            skip_days=skip_days,
            description=description,
            expires_after=expires_after,
            destination_channel=destination_channel,
            ephemeral=ephemeral,
            timezone=timezone,
        )

    @reminder_group.command(
        name="list",
        description="View reminders for this server.",
    )
    @app_commands.describe(
        scope="Which reminders to show",
        destination_channel="Channel to filter by when scope is Specific Channel",
        status="Filter reminders by status",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        scope=_REMINDER_LIST_SCOPE_CHOICES,
        status=_REMINDER_LIST_STATUS_CHOICES,
        visibility=VISIBILITY_CHOICES,
    )
    async def reminder_list(
        self,
        interaction: discord.Interaction,
        scope: Optional[app_commands.Choice[str]] = None,
        destination_channel: Optional[discord.TextChannel] = None,
        status: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        selected_channel_id, scope_label = self._resolve_reminder_list_scope(
            interaction,
            scope,
            destination_channel,
            ephemeral=ephemeral,
        )
        paused_filter, status_label = self._resolve_reminder_list_status(status)

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            reminders = await asyncio.to_thread(
                ReminderFunctions.list_reminders,
                interaction.guild_id,
                paused_filter,
                selected_channel_id,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while loading reminders.",
                ephemeral=ephemeral,
                cause=exc,
            )
        reminders = filter_visible_items(
            interaction,
            reminders,
            channel_id_getter=lambda reminder: reminder.channel_id,
        )

        view = ReminderListView(
            reminders=reminders,
            scope_label=scope_label,
            status_label=status_label,
            guild_id=interaction.guild_id,
            channel_id=selected_channel_id,
            paused_filter=paused_filter,
            user_id=interaction.user.id,
            response_ephemeral=ephemeral,
        )
        if not reminders:
            await interaction.followup.send(
                ephemeral=ephemeral,
                **view.payload(),
            )
            return

        await interaction.followup.send(
            ephemeral=ephemeral,
            view=view,
            **view.payload(),
        )

    @reminder_group.command(
        name="remove",
        description="Remove a scheduled reminder by ID.",
    )
    @app_commands.describe(
        reminder_id="Reminder ID",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_remove(
        self,
        interaction: discord.Interaction,
        reminder_id: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        reminder_id_value = reminder_id.strip()

        await self._get_visible_reminder(
            interaction,
            reminder_id_value,
            ephemeral=ephemeral,
        )

        deleted = await asyncio.to_thread(
            ReminderFunctions.delete_reminder,
            reminder_id_value,
            interaction.guild_id,
        )

        if not deleted:
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        await interaction.followup.send(
            ephemeral=ephemeral,
            **DailyTaskEmbeds.reminder_embed(
                f"Deleted reminder `{reminder_id.strip()}`.",
                ok=True,
            ),
        )

    @reminder_group.command(
        name="edit",
        description="Edit an existing reminder.",
    )
    @app_commands.describe(
        reminder="Reminder from autocomplete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_edit(
        self,
        interaction: discord.Interaction,
        reminder: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        job = await self._get_visible_reminder(
            interaction,
            reminder,
            ephemeral=ephemeral,
        )

        try:
            channel_options = _build_text_channel_select_options(
                interaction.guild,
                job.channel_id,
            )
            await interaction.response.send_modal(
                ReminderEditModal(
                    job,
                    channel_options=channel_options,
                    response_ephemeral=ephemeral,
                )
            )
        except discord.HTTPException as exc:
            raise UserVisibleError(
                "Something went wrong while opening the edit dialog.",
                ephemeral=ephemeral,
                cause=exc,
            )

    @reminder_group.command(
        name="show",
        description="Show a specific reminder.",
    )
    @app_commands.describe(
        reminder="Reminder from autocomplete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_show(
        self,
        interaction: discord.Interaction,
        reminder: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        job = await self._get_visible_reminder(
            interaction,
            reminder,
            ephemeral=ephemeral,
        )

        await self._send_reminder_output(
            interaction,
            job=job,
            result_message=f"Showing reminder `{str(job.id)}`.",
            ephemeral=ephemeral,
        )

    @reminder_group.command(
        name="pause",
        description="Pause a reminder by ID.",
    )
    @app_commands.describe(
        reminder_id="Reminder ID",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_pause(
        self,
        interaction: discord.Interaction,
        reminder_id: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        reminder_id_value = reminder_id.strip()

        await self._get_visible_reminder(
            interaction,
            reminder_id_value,
            ephemeral=ephemeral,
        )
        result = await asyncio.to_thread(
            ReminderFunctions.pause_reminder,
            reminder_id_value,
            interaction.guild_id,
        )

        if result == "missing":
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        paused_job = await self._get_visible_reminder(
            interaction,
            reminder_id_value,
            ephemeral=ephemeral,
        )

        if result == "already_paused":
            await self._send_reminder_output(
                interaction,
                job=paused_job,
                result_message=f"Reminder `{reminder_id_value}` is already paused.",
                ephemeral=ephemeral,
            )
            return

        await self._send_reminder_output(
            interaction,
            job=paused_job,
            result_message=f"Paused reminder `{reminder_id_value}`.",
            ephemeral=ephemeral,
        )

    @reminder_group.command(
        name="resume",
        description="Resume a paused reminder by ID.",
    )
    @app_commands.describe(
        reminder_id="Reminder ID",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_resume(
        self,
        interaction: discord.Interaction,
        reminder_id: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)

        reminder_id_value = reminder_id.strip()

        await self._get_visible_reminder(
            interaction,
            reminder_id_value,
            ephemeral=ephemeral,
        )
        result = await asyncio.to_thread(
            ReminderFunctions.resume_reminder,
            reminder_id_value,
            interaction.guild_id,
        )

        if result == "missing":
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        resumed_job = await self._get_visible_reminder(
            interaction,
            reminder_id_value,
            ephemeral=ephemeral,
        )

        if result == "already_resumed":
            await self._send_reminder_output(
                interaction,
                job=resumed_job,
                result_message=f"Reminder `{reminder_id_value}` is already active.",
                ephemeral=ephemeral,
            )
            return

        await self._send_reminder_output(
            interaction,
            job=resumed_job,
            result_message=f"Resumed reminder `{reminder_id_value}`.",
            ephemeral=ephemeral,
        )

    @reminder_group.command(
        name="customize",
        description="Set a custom reminder bot username and avatar.",
    )
    @app_commands.describe(
        username="Custom reminder bot username",
        avatar_url="Custom reminder bot avatar URL",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_customize(
        self,
        interaction: discord.Interaction,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await self._send_not_implemented(
            interaction,
            "/reminder customize",
            ephemeral=ephemeral,
        )

    async def _create_reminder_from_options(
        self,
        interaction: discord.Interaction,
        reminder: str,
        time: str,
        repeat: Optional[str],
        ping: Optional[discord.Member | discord.Role],
        thumbnail_url: Optional[str],
        skip_days: Optional[str],
        description: Optional[str],
        expires_after: Optional[str],
        destination_channel: Optional[discord.TextChannel],
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        ping_text = ping.mention if ping is not None else None
        destination_channel_id = (
            destination_channel.id if destination_channel is not None else None
        )
        created_job, confirmation = await asyncio.to_thread(
            ReminderFunctions.create_reminder,
            interaction.guild_id,
            interaction.channel_id,
            reminder,
            time,
            repeat,
            ping_text,
            thumbnail_url,
            skip_days,
            description,
            expires_after,
            destination_channel_id,
            ephemeral,
            timezone,
        )
        await self._send_reminder_output(
            interaction,
            job=created_job,
            result_message=confirmation,
            ephemeral=ephemeral,
        )

    def _resolve_reminder_list_scope(
        self,
        interaction: discord.Interaction,
        scope: Optional[app_commands.Choice[str]],
        destination_channel: Optional[discord.TextChannel],
        *,
        ephemeral: bool,
    ) -> tuple[Optional[int], str]:
        scope_value = scope.value if scope else (
            "all" if interaction.guild is not None else "current"
        )

        if interaction.guild is None:
            if not interaction.channel_id:
                raise ValidationError(
                    "This conversation does not have a destination channel.",
                    ephemeral=ephemeral,
                )
            if scope_value == "all":
                raise ValidationError(
                    "All server reminders are only available in servers.",
                    ephemeral=ephemeral,
                )
            return interaction.channel_id, "This DM"

        if scope_value == "all":
            if destination_channel is not None:
                raise ValidationError(
                    "`destination_channel` only applies when scope is `Specific Channel`.",
                    ephemeral=ephemeral,
                )
            return None, "All server reminders"

        if scope_value == "current":
            if destination_channel is not None:
                raise ValidationError(
                    "`destination_channel` only applies when scope is `Specific Channel`.",
                    ephemeral=ephemeral,
                )
            current_channel = interaction.channel
            if not isinstance(current_channel, discord.TextChannel):
                raise ValidationError(
                    "This command must be used in a text channel for `This Channel` scope.",
                    ephemeral=ephemeral,
                )
            return current_channel.id, f"#{current_channel.name}"

        if scope_value != "channel":
            raise ValidationError(
                "Please select a valid scope.",
                ephemeral=ephemeral,
            )

        if destination_channel is None:
            raise ValidationError(
                "Choose a channel when scope is `Specific Channel`.",
                ephemeral=ephemeral,
            )

        channel_id = destination_channel.id
        if not can_view_channel(interaction, channel_id):
            raise ValidationError(
                "That channel was not found.",
                ephemeral=ephemeral,
            )

        return channel_id, f"#{destination_channel.name}"

    @staticmethod
    def _resolve_reminder_list_status(
        status: Optional[app_commands.Choice[str]],
    ) -> tuple[Optional[bool], str]:
        status_value = status.value if status else "all"
        if status_value == "active":
            return False, "Active"
        if status_value == "paused":
            return True, "Paused"
        return None, "All"

    async def _reminder_id_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
        *,
        paused: Optional[bool] = None,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        try:
            reminders = await asyncio.to_thread(
                ReminderFunctions.list_reminders,
                interaction.guild_id,
                paused,
            )
        except Exception:
            return []
        reminders = filter_visible_items(
            interaction,
            reminders,
            channel_id_getter=lambda reminder: reminder.channel_id,
        )

        options: List[app_commands.Choice[str]] = []
        for job in reminders:
            label = ReminderFunctions.reminder_label(job)
            job_id = str(job.id)
            search_text = f"{label} {job_id}".lower()
            if query and query not in search_text:
                continue

            choice_name = f"{label} [{job_id[:8]}]"
            options.append(
                app_commands.Choice(
                    name=choice_name[:100],
                    value=job_id,
                )
            )
            if len(options) >= 25:
                break

        return options[:25]

    @reminder_remove.autocomplete("reminder_id")
    async def reminder_remove_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_id_autocomplete(interaction, current)

    @reminder_edit.autocomplete("reminder")
    async def reminder_edit_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_id_autocomplete(interaction, current)

    @reminder_show.autocomplete("reminder")
    async def reminder_show_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_id_autocomplete(interaction, current)

    @reminder_pause.autocomplete("reminder_id")
    async def reminder_pause_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_id_autocomplete(
            interaction,
            current,
            paused=False,
        )

    @reminder_resume.autocomplete("reminder_id")
    async def reminder_resume_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_id_autocomplete(
            interaction,
            current,
            paused=True,
        )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(ReminderCog(client))
    client.tree.add_command(create_reminder_from_message)
