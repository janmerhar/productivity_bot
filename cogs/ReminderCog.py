import asyncio
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.ReminderFunctions import ReminderFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.error_reporting import UserVisibleError
from services.error_reporting import ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility
from views.ReminderEditModal import (
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
        destination_channel="Filter reminders by destination channel",
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
        destination_channel: Optional[str] = None,
        status: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        selected_channel_id, scope_label = self._resolve_reminder_list_destination(
            interaction,
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

        try:
            deleted = await asyncio.to_thread(
                ReminderFunctions.delete_reminder,
                reminder_id,
                interaction.guild_id,
            )
        except ValueError as exc:
            raise ValidationError(
                "That reminder ID is invalid.",
                ephemeral=ephemeral,
                cause=exc,
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

        if job is None:
            raise ValidationError(
                "No reminder found with that ID in this server.",
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

        if job is None:
            raise ValidationError(
                "No reminder found with that ID in this server.",
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
        description="Pause reminders by ID or all at once.",
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

        if reminder_id_value == ReminderFunctions.ALL_REMINDERS_TOKEN:
            paused_count = await asyncio.to_thread(
                ReminderFunctions.pause_all_reminders,
                interaction.guild_id,
            )
            if paused_count == 0:
                await interaction.followup.send(
                    ephemeral=ephemeral,
                    **DailyTaskEmbeds.reminder_embed(
                        "There are no active reminders to pause.",
                        ok=True,
                    ),
                )
                return

            await interaction.followup.send(
                ephemeral=ephemeral,
                **DailyTaskEmbeds.reminder_embed(
                    f"Paused {paused_count} reminder(s).",
                    ok=True,
                ),
            )
            return

        try:
            result = await asyncio.to_thread(
                ReminderFunctions.pause_reminder,
                reminder_id_value,
                interaction.guild_id,
            )
        except ValueError as exc:
            raise ValidationError(
                "That reminder ID is invalid.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if result == "missing":
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        paused_job = await asyncio.to_thread(
            ReminderFunctions.get_reminder,
            reminder_id_value,
            interaction.guild_id,
        )
        if paused_job is None:
            raise UserVisibleError(
                "Reminder status changed, but it could not be reloaded.",
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
        description="Resume paused reminders by ID or all at once.",
    )
    @app_commands.describe(
        reminder_id="Reminder ID",
        all="Resume all reminders",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_resume(
        self,
        interaction: discord.Interaction,
        reminder_id: Optional[str] = None,
        all: Optional[bool] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)

        reminder_id_value = (reminder_id or "").strip()
        resume_all = bool(all) or (
            reminder_id_value == ReminderFunctions.ALL_REMINDERS_TOKEN
        )

        if reminder_id_value == ReminderFunctions.ALL_REMINDERS_TOKEN:
            reminder_id_value = ""

        if reminder_id_value and resume_all:
            raise ValidationError(
                "Choose either a reminder ID or `all=true`, not both.",
                ephemeral=ephemeral,
            )

        if resume_all:
            resumed_count = await asyncio.to_thread(
                ReminderFunctions.resume_all_reminders,
                interaction.guild_id,
            )
            if resumed_count == 0:
                await interaction.followup.send(
                    ephemeral=ephemeral,
                    **DailyTaskEmbeds.reminder_embed(
                        "There are no paused reminders to resume.",
                        ok=True,
                    ),
                )
                return

            await interaction.followup.send(
                ephemeral=ephemeral,
                **DailyTaskEmbeds.reminder_embed(
                    f"Resumed {resumed_count} reminder(s).",
                    ok=True,
                ),
            )
            return

        if not reminder_id_value:
            raise ValidationError(
                "Provide a reminder ID or use `all=true`.",
                ephemeral=ephemeral,
            )

        try:
            result = await asyncio.to_thread(
                ReminderFunctions.resume_reminder,
                reminder_id_value,
                interaction.guild_id,
            )
        except ValueError as exc:
            raise ValidationError(
                "That reminder ID is invalid.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if result == "missing":
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        resumed_job = await asyncio.to_thread(
            ReminderFunctions.get_reminder,
            reminder_id_value,
            interaction.guild_id,
        )
        if resumed_job is None:
            raise UserVisibleError(
                "Reminder status changed, but it could not be reloaded.",
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

    def _resolve_reminder_list_destination(
        self,
        interaction: discord.Interaction,
        destination_channel: Optional[str],
        *,
        ephemeral: bool,
    ) -> tuple[Optional[int], str]:
        raw_value = (destination_channel or "").strip()
        normalized = raw_value.lower()

        if interaction.guild is None:
            if not interaction.channel_id:
                raise ValidationError(
                    "This conversation does not have a destination channel.",
                    ephemeral=ephemeral,
                )
            if normalized and normalized not in {
                "all",
                "server",
                f"channel:{interaction.channel_id}",
            }:
                raise ValidationError(
                    "Please select a valid destination from autocomplete.",
                    ephemeral=ephemeral,
                )
            return interaction.channel_id, "This DM"

        if not normalized or normalized in {"all", "server"}:
            return None, "All server reminders"

        if not normalized.startswith("channel:"):
            raise ValidationError(
                "Please select a valid destination from autocomplete.",
                ephemeral=ephemeral,
            )

        try:
            channel_id = int(normalized.split(":", 1)[1])
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                "Please select a valid destination from autocomplete.",
                ephemeral=ephemeral,
                cause=exc,
            )

        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            raise ValidationError(
                "That channel was not found.",
                ephemeral=ephemeral,
            )
        if not isinstance(channel, discord.TextChannel):
            raise ValidationError(
                "Please select a text channel from autocomplete.",
                ephemeral=ephemeral,
            )

        return channel_id, f"#{channel.name}"

    def _build_reminder_destination_autocomplete_options(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        options: List[app_commands.Choice[str]] = []
        current_channel = interaction.channel
        current_text_channel_id = (
            current_channel.id
            if isinstance(current_channel, discord.TextChannel)
            else None
        )
        current_channel_name = getattr(current_channel, "name", None)

        if interaction.guild is None:
            current_dm_channel_id = interaction.channel_id
            if current_dm_channel_id and (
                not query
                or "dm" in query
                or "this" in query
                or "channel" in query
            ):
                options.append(
                    app_commands.Choice(
                        name="This DM",
                        value=f"channel:{current_dm_channel_id}",
                    )
                )
            return options[:25]

        base_options = [
            app_commands.Choice(name="All Server Reminders", value="all"),
        ]
        if current_text_channel_id:
            current_label = (
                f"This Channel (#{current_channel_name})"
                if current_channel_name
                else "This Channel"
            )
            base_options.append(
                app_commands.Choice(
                    name=current_label[:100],
                    value=f"channel:{current_text_channel_id}",
                )
            )

        for option in base_options:
            if not query or query in option.name.lower():
                options.append(option)

        for channel in interaction.guild.text_channels:
            if len(options) >= 25:
                break
            if current_text_channel_id and channel.id == current_text_channel_id:
                continue
            if query and query not in channel.name.lower() and query not in str(channel.id):
                continue
            permissions = channel.permissions_for(interaction.user)
            if not permissions.view_channel or not permissions.send_messages:
                continue
            options.append(
                app_commands.Choice(
                    name=f"#{channel.name}"[:100],
                    value=f"channel:{channel.id}",
                )
            )

        return options[:25]

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
        include_all: bool = False,
        all_label: str = "All",
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        if interaction.guild_id is None:
            return []

        try:
            reminders = await asyncio.to_thread(
                ReminderFunctions.list_reminders,
                interaction.guild_id,
                paused,
            )
        except Exception:
            return []

        options: List[app_commands.Choice[str]] = []
        if include_all:
            all_search_text = all_label.lower()
            if not query or query in all_search_text or "all".startswith(query):
                options.append(
                    app_commands.Choice(
                        name=all_label[:100],
                        value=ReminderFunctions.ALL_REMINDERS_TOKEN,
                    )
                )

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

    @reminder_list.autocomplete("destination_channel")
    async def reminder_list_destination_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return self._build_reminder_destination_autocomplete_options(
            interaction,
            current,
        )

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
            include_all=True,
            all_label="All active reminders",
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
            include_all=True,
            all_label="All paused reminders",
        )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(ReminderCog(client))
