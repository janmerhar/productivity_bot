import asyncio
from typing import Callable, List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.ReminderFunctions import ReminderFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.channel_visibility import can_view_channel
from services.discord_helpers import (
    resolve_ephemeral_from_scope,
    normalize_reminder_destination,
    reminder_destination_autocomplete,
)
from services.error_reporting import UserVisibleError
from services.error_reporting import ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility
from views.ReminderEditModal import (
    ReminderCreateModal,
    ReminderEditModal,
    ReminderPingModal,
    _build_destination_select_options,
)
from views.ReminderListView import ReminderListView
from views.ReminderOutputView import ReminderOutputView

_REMINDER_LIST_STATUS_CHOICES = [
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="Active", value="active"),
    app_commands.Choice(name="Paused", value="paused"),
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
            guild=interaction.guild,
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
        reminder: str,
        *,
        ephemeral: bool,
    ):
        try:
            job = await asyncio.to_thread(
                ReminderFunctions.get_reminder,
                reminder,
                interaction.guild_id,
            )
        except ValueError as exc:
            raise ValidationError(
                "That reminder ID is invalid.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if job is None or not self._can_view_reminder(interaction, job):
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        return job

    async def _list_visible_reminders(
        self,
        interaction: discord.Interaction,
        *,
        paused: Optional[bool] = None,
        ephemeral: bool = True,
    ):
        try:
            reminders = await asyncio.to_thread(
                ReminderFunctions.list_reminders,
                interaction.guild_id if interaction.guild_id is not None else None,
                paused,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while loading reminders.",
                ephemeral=ephemeral,
                cause=exc,
            )
        return self._filter_visible_reminders(interaction, reminders)

    @staticmethod
    def _is_all_reminders_value(reminder: str) -> bool:
        normalized_reminder = reminder.strip().lower()
        return normalized_reminder in {
            "all",
            ReminderFunctions.ALL_REMINDERS_TOKEN.lower(),
        }

    async def _send_bulk_reminder_result(
        self,
        interaction: discord.Interaction,
        *,
        count: int,
        action: str,
        ephemeral: bool,
    ) -> None:
        reminder_label = "reminder" if count == 1 else "reminders"
        await interaction.followup.send(
            ephemeral=ephemeral,
            **DailyTaskEmbeds.reminder_embed(
                f"{action} {count} {reminder_label}.",
                ok=True,
            ),
        )

    async def _apply_bulk_reminder_action(
        self,
        interaction: discord.Interaction,
        *,
        paused: bool,
        action_fn: Callable[[str, Optional[int]], str],
        success_result: str,
        empty_message: str,
        success_message: str,
        ephemeral: bool,
    ) -> None:
        reminders = await self._list_visible_reminders(
            interaction,
            paused=paused,
            ephemeral=ephemeral,
        )
        if not reminders:
            raise ValidationError(
                empty_message,
                ephemeral=ephemeral,
            )

        changed_count = 0
        for job in reminders:
            result = await asyncio.to_thread(
                action_fn,
                str(job.id),
                interaction.guild_id,
            )
            if result == success_result:
                changed_count += 1

        if changed_count == 0:
            raise ValidationError(
                empty_message,
                ephemeral=ephemeral,
            )

        await self._send_bulk_reminder_result(
            interaction,
            count=changed_count,
            action=success_message,
            ephemeral=ephemeral,
        )

    async def _apply_single_reminder_action(
        self,
        interaction: discord.Interaction,
        *,
        reminder: str,
        action_fn: Callable[[str, Optional[int]], str],
        already_result: str,
        success_message: str,
        already_message: str,
        missing_message: str,
        ephemeral: bool,
    ) -> None:
        await self._get_visible_reminder(
            interaction,
            reminder,
            ephemeral=ephemeral,
        )
        result = await asyncio.to_thread(
            action_fn,
            reminder,
            interaction.guild_id,
        )

        if result == "missing":
            raise ValidationError(
                missing_message,
                ephemeral=ephemeral,
            )

        job = await self._get_visible_reminder(
            interaction,
            reminder,
            ephemeral=ephemeral,
        )

        result_message = (
            already_message.format(reminder=reminder)
            if result == already_result
            else success_message.format(reminder=reminder)
        )
        await self._send_reminder_output(
            interaction,
            job=job,
            result_message=result_message,
            ephemeral=ephemeral,
        )

    async def _apply_reminder_action(
        self,
        interaction: discord.Interaction,
        *,
        reminder: str,
        list_paused: bool,
        action_fn: Callable[[str, Optional[int]], str],
        success_result: str,
        already_result: str,
        success_message: str,
        already_message: str,
        empty_bulk_message: str,
        bulk_success_message: str,
        missing_message: str,
        ephemeral: bool,
    ) -> None:
        if self._is_all_reminders_value(reminder):
            await self._apply_bulk_reminder_action(
                interaction,
                paused=list_paused,
                action_fn=action_fn,
                success_result=success_result,
                empty_message=empty_bulk_message,
                success_message=bulk_success_message,
                ephemeral=ephemeral,
            )
            return

        await self._apply_single_reminder_action(
            interaction,
            reminder=reminder,
            action_fn=action_fn,
            already_result=already_result,
            success_message=success_message,
            already_message=already_message,
            missing_message=missing_message,
            ephemeral=ephemeral,
        )

    @staticmethod
    def _can_view_reminder(
        interaction: discord.Interaction,
        job,
    ) -> bool:
        if ReminderFunctions.is_private_destination(job):
            return ReminderFunctions.destination_user_id(job) == interaction.user.id
        return can_view_channel(interaction, job.channel_id)

    def _filter_visible_reminders(
        self,
        interaction: discord.Interaction,
        reminders,
    ):
        return [
            reminder
            for reminder in reminders
            if self._can_view_reminder(interaction, reminder)
        ]

    @reminder_group.command(
        name="add",
        description="Create a one-time or recurring reminder.",
    )
    @app_commands.describe(
        reminder="Reminder title or primary content",
        schedule="Cron expression or natural language schedule",
        add_pings="Open a modal to select multiple user pings",
        description="Reminder description",
        expires="Stop sending after this time",
        destination="Destination channel or private delivery",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        visibility=VISIBILITY_CHOICES,
    )
    async def reminder_add(
        self,
        interaction: discord.Interaction,
        reminder: str,
        schedule: str,
        add_pings: bool = False,
        description: Optional[str] = None,
        expires: Optional[str] = None,
        destination: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        try:
            destination_type, destination_channel_id, _ = normalize_reminder_destination(
                interaction,
                destination,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

        if add_pings:
            if interaction.guild is None:
                raise ValidationError(
                    "`add_pings` is only available in servers.",
                    ephemeral=True,
                )

            setup_default_channel_id = (
                destination_channel_id
                if destination_type == "channel" and destination_channel_id is not None
                else interaction.channel_id
            )
            try:
                await interaction.response.send_modal(
                    ReminderPingModal(
                        guild=interaction.guild,
                        guild_id=interaction.guild_id,
                        default_channel_id=setup_default_channel_id,
                        reminder=reminder,
                        schedule=schedule,
                        description=description,
                        until=expires,
                        destination_type=destination_type,
                        destination_channel_id=destination_channel_id,
                        response_ephemeral=ephemeral,
                        user_id=interaction.user.id,
                    )
                )
            except discord.HTTPException as exc:
                raise UserVisibleError(
                    "Something went wrong while opening the ping picker.",
                    ephemeral=ephemeral,
                    cause=exc,
                )
            return

        needs_timezone = ReminderFunctions.needs_timezone(
            schedule,
            expires=expires,
        )

        async def _continue_with_timezone(
            followup_interaction: discord.Interaction,
            resolved_timezone: str,
        ) -> None:
            await self._create_reminder_from_options(
                interaction=followup_interaction,
                reminder=reminder,
                schedule=schedule,
                description=description,
                expires=expires,
                destination_type=destination_type,
                destination_channel_id=destination_channel_id,
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
            schedule=schedule,
            description=description,
            expires=expires,
            destination_type=destination_type,
            destination_channel_id=destination_channel_id,
            ephemeral=ephemeral,
            timezone=timezone,
        )

    @reminder_group.command(
        name="list",
        description="View reminders.",
    )
    @app_commands.describe(
        channel="Which channel or private destination to show",
        status="Filter reminders by status",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        status=_REMINDER_LIST_STATUS_CHOICES,
        visibility=VISIBILITY_CHOICES,
    )
    async def reminder_list(
        self,
        interaction: discord.Interaction,
        channel: Optional[str] = None,
        status: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        (
            target_value,
            selected_channel_id,
            destination_type,
            scope_label,
        ) = self._resolve_reminder_list_target(
            interaction,
            channel,
        )
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            target_value,
            visibility,
            private_scope_values=("private",),
            guild_default_visibility="public",
            dm_default_visibility="public",
        )
        paused_filter, status_label = self._resolve_reminder_list_status(status)

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            reminders = await asyncio.to_thread(
                ReminderFunctions.list_reminders,
                interaction.guild_id if interaction.guild_id is not None else None,
                paused_filter,
                selected_channel_id,
                destination_type,
                interaction.user.id if target_value == "private" else None,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while loading reminders.",
                ephemeral=ephemeral,
                cause=exc,
            )
        reminders = self._filter_visible_reminders(interaction, reminders)

        view = ReminderListView(
            reminders=reminders,
            scope_label=scope_label,
            status_label=status_label,
            guild_id=interaction.guild_id if interaction.guild_id is not None else None,
            channel_id=selected_channel_id,
            destination_type=destination_type,
            paused_filter=paused_filter,
            user_id=interaction.user.id,
            response_ephemeral=ephemeral,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **view.payload(),
        )

    @reminder_group.command(
        name="remove",
        description="Remove a scheduled reminder by ID.",
    )
    @app_commands.describe(
        reminder="Reminder ID",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_remove(
        self,
        interaction: discord.Interaction,
        reminder: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        reminder_value = reminder.strip()

        await self._get_visible_reminder(
            interaction,
            reminder_value,
            ephemeral=ephemeral,
        )

        deleted = await asyncio.to_thread(
            ReminderFunctions.delete_reminder,
            reminder_value,
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
                f"Deleted reminder `{reminder_value}`.",
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
            channel_options = _build_destination_select_options(
                interaction.guild,
                job.channel_id,
                is_private_selected=ReminderFunctions.is_private_destination(job),
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
        description="Pause a reminder by ID, or all active reminders.",
    )
    @app_commands.describe(
        reminder="Reminder ID",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_pause(
        self,
        interaction: discord.Interaction,
        reminder: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        await self._apply_reminder_action(
            interaction,
            reminder=reminder.strip(),
            list_paused=False,
            action_fn=ReminderFunctions.pause_reminder,
            success_result="paused",
            already_result="already_paused",
            success_message="Paused reminder `{reminder}`.",
            already_message="Reminder `{reminder}` is already paused.",
            empty_bulk_message="No active reminders found that you can pause.",
            bulk_success_message="Paused",
            missing_message="No reminder found with that ID in this server.",
            ephemeral=ephemeral,
        )

    @reminder_group.command(
        name="resume",
        description="Resume a paused reminder by ID, or all paused reminders.",
    )
    @app_commands.describe(
        reminder="Reminder ID",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_resume(
        self,
        interaction: discord.Interaction,
        reminder: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        await self._apply_reminder_action(
            interaction,
            reminder=reminder.strip(),
            list_paused=True,
            action_fn=ReminderFunctions.resume_reminder,
            success_result="resumed",
            already_result="already_resumed",
            success_message="Resumed reminder `{reminder}`.",
            already_message="Reminder `{reminder}` is already active.",
            empty_bulk_message="No paused reminders found that you can resume.",
            bulk_success_message="Resumed",
            missing_message="No reminder found with that ID in this server.",
            ephemeral=ephemeral,
        )

    async def _create_reminder_from_options(
        self,
        interaction: discord.Interaction,
        reminder: str,
        schedule: str,
        description: Optional[str],
        expires: Optional[str],
        destination_type: str,
        destination_channel_id: Optional[int],
        ephemeral: bool,
        timezone: Optional[str],
        thumbnail_url: Optional[str] = None,
    ) -> None:
        created_job, confirmation = await asyncio.to_thread(
            ReminderFunctions.create_reminder,
            guild_id=interaction.guild_id,
            default_channel_id=interaction.channel_id,
            reminder=reminder,
            schedule=schedule,
            thumbnail_url=thumbnail_url,
            description=description,
            expires=expires,
            destination_channel_id=destination_channel_id,
            destination_type=destination_type,
            destination_user_id=interaction.user.id,
            ephemeral=ephemeral,
            timezone=timezone,
        )
        await self._send_reminder_output(
            interaction,
            job=created_job,
            result_message=confirmation,
            ephemeral=ephemeral,
        )

    def _build_reminder_list_target_autocomplete_options(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        options: List[app_commands.Choice[str]] = []

        base_options = [
            app_commands.Choice(name="This Channel", value="channel"),
            app_commands.Choice(name="Private option", value="private"),
        ]
        if interaction.guild is not None:
            base_options.insert(
                1,
                app_commands.Choice(
                    name="All Server Reminders",
                    value="all_server",
                ),
            )

        options.extend(
            option for option in base_options if not query or query in option.name.lower()
        )

        guild = interaction.guild
        if guild is None:
            return [
                option
                for option in options
                if option.value == "private"
            ][:25]

        for channel in guild.text_channels:
            if len(options) >= 25:
                break
            channel_name = getattr(channel, "name", None)
            channel_id = getattr(channel, "id", None)
            if channel_name is None or channel_id is None:
                continue
            if query and query not in channel_name.lower() and query not in str(channel_id):
                continue
            permissions = channel.permissions_for(interaction.user)
            if not permissions.view_channel:
                continue
            options.append(
                app_commands.Choice(
                    name=f"#{channel_name}"[:100],
                    value=f"channel:{channel_id}",
                )
            )

        return options[:25]

    def _resolve_reminder_list_target(
        self,
        interaction: discord.Interaction,
        channel: Optional[str],
    ) -> tuple[str, Optional[int], str, str]:
        target_value = (channel or "").strip()
        if not target_value:
            target_value = "channel" if interaction.guild is not None else "private"

        if interaction.guild is None:
            if target_value != "private":
                raise ValidationError(
                    "Only `Private option` is available in DMs.",
                    ephemeral=True,
                )
            return "private", None, "private", "Private option"

        if target_value.startswith("channel:"):
            try:
                channel_id = int(target_value.split(":", 1)[1])
            except (ValueError, IndexError):
                raise ValidationError(
                    "Please select a valid channel from autocomplete.",
                    ephemeral=True,
                )
            selected_channel = interaction.guild.get_channel(channel_id)
            if selected_channel is None:
                raise ValidationError(
                    "That channel was not found.",
                    ephemeral=True,
                )
            if not isinstance(selected_channel, discord.TextChannel):
                raise ValidationError(
                    "Please select a text channel from autocomplete.",
                    ephemeral=True,
                )
            if not can_view_channel(interaction, channel_id):
                raise ValidationError(
                    "That channel was not found.",
                    ephemeral=True,
                )
            return "channel", channel_id, "channel", f"#{selected_channel.name}"

        if target_value == "all_server":
            return "all_server", None, "channel", "All Server Reminders"

        if target_value == "private":
            return "private", None, "private", "Private option"

        if target_value != "channel":
            raise ValidationError(
                "Please select a valid list from autocomplete.",
                ephemeral=True,
            )

        current_channel = interaction.channel
        if not isinstance(current_channel, discord.TextChannel):
            raise ValidationError(
                "This command must be used in a text channel for `This Channel`.",
                ephemeral=True,
            )
        return "channel", current_channel.id, "channel", f"#{current_channel.name}"

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

    async def _reminder_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
        *,
        paused: Optional[bool] = None,
        include_all_option: bool = False,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        options: List[app_commands.Choice[str]] = []
        if include_all_option:
            all_search_text = "all"
            all_choice = app_commands.Choice(
                name="All",
                value="all",
            )
            if not query or query in all_search_text:
                options.append(all_choice)

        try:
            reminders = await self._list_visible_reminders(
                interaction,
                paused=paused,
            )
        except UserVisibleError:
            return []

        for job in reminders:
            if len(options) >= 25:
                break
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

        return options[:25]

    @reminder_add.autocomplete("destination")
    async def reminder_add_destination_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return reminder_destination_autocomplete(interaction, current)

    @reminder_list.autocomplete("channel")
    async def reminder_list_target_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return self._build_reminder_list_target_autocomplete_options(
            interaction,
            current,
        )

    @reminder_remove.autocomplete("reminder")
    async def reminder_remove_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_autocomplete(interaction, current)

    @reminder_edit.autocomplete("reminder")
    async def reminder_edit_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_autocomplete(interaction, current)

    @reminder_show.autocomplete("reminder")
    async def reminder_show_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_autocomplete(interaction, current)

    @reminder_pause.autocomplete("reminder")
    async def reminder_pause_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_autocomplete(
            interaction,
            current,
            paused=False,
            include_all_option=True,
        )

    @reminder_resume.autocomplete("reminder")
    async def reminder_resume_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._reminder_autocomplete(
            interaction,
            current,
            paused=True,
            include_all_option=True,
        )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(ReminderCog(client))
    client.tree.add_command(create_reminder_from_message)
