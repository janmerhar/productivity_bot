import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds.HabitEmbeds import HabitEmbeds
from classes.HabitFunctions import HabitFunctions
from views.HabitActionView import HabitActionView
from views.HabitListView import HabitListView
from views.HabitCreateModal import HabitCreateModal, HabitCreatedActionView
from services.discord_helpers import (
    habit_list_scope_autocomplete,
    habit_target_autocomplete,
    normalize_habit_target,
    normalize_habit_list_scope,
    resolve_habit_ephemeral,
)
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import (
    VISIBILITY_CHOICES,
    VISIBILITY_DESC,
)


class HabitCog(commands.Cog):
    habit_group = app_commands.Group(name="habit", description="Manage habits")

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @staticmethod
    def _resolve_response_visibility(
        interaction: discord.Interaction,
        scope_value: str,
        visibility: Optional[app_commands.Choice[str]],
    ) -> bool:
        return resolve_habit_ephemeral(
            interaction.guild_id,
            scope_value,
            visibility,
        )

    @staticmethod
    def _default_scope_value(interaction: discord.Interaction) -> str:
        return "channel" if interaction.guild_id is not None else "personal"

    @staticmethod
    def _habit_choice_label(habit: dict) -> str:
        name = str(habit.get("name") or "Habit").strip() or "Habit"
        created = HabitFunctions._parse_timestamp(habit.get("created"))
        created_text = (
            created.strftime("%Y-%m-%d") if created is not None else "unknown"
        )
        habit_id = str(habit.get("_id") or "").strip()
        suffix = habit_id[-6:] if habit_id else "habit"
        label = f"{name} | {created_text} | {suffix}"
        return label[:100]

    def _build_created_habit_view(
        self,
        document: dict,
        *,
        ephemeral: bool,
    ) -> HabitCreatedActionView:
        return HabitCreatedActionView(
            self,
            habit_id=str(document.get("_id") or ""),
            habit_name=str(document.get("name") or "Habit"),
            user_id=int(document.get("user_id") or 0),
            scope_value=HabitFunctions._normalize_scope(
                str(document.get("scope") or "channel")
            ),
            target_channel_id=document.get("channel_id"),
            response_ephemeral=ephemeral,
            today_status=HabitFunctions.today_status(document),
        )

    async def _resolve_habit_reference(
        self,
        interaction: discord.Interaction,
        reference: str,
        *,
        scope_value: str,
        ephemeral: bool,
    ) -> dict:
        cleaned_reference = str(reference or "").strip()
        if not cleaned_reference:
            raise ValidationError(
                "Habit name cannot be empty.",
                ephemeral=ephemeral,
            )

        habit = await asyncio.to_thread(
            HabitFunctions.fetch_habit_in_scope,
            cleaned_reference,
            interaction.guild_id,
            interaction.user.id,
            interaction.channel_id,
            scope_value,
        )
        if habit is not None:
            return habit

        matches = await asyncio.to_thread(
            HabitFunctions.find_habits_by_name,
            interaction.guild_id,
            interaction.user.id,
            interaction.channel_id,
            cleaned_reference,
            scope_value,
        )
        if len(matches) > 1:
            raise ValidationError(
                "Multiple habits in this scope have that name. Use autocomplete to pick the exact one.",
                ephemeral=ephemeral,
            )
        if not matches:
            raise ValidationError(
                "No matching habit found in this scope.",
                hint="Use autocomplete or run `/habit list` first.",
                ephemeral=ephemeral,
            )
        return matches[0]

    async def _habit_reference_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        scope_value = self._default_scope_value(interaction)
        habits = await asyncio.to_thread(
            HabitFunctions.autocomplete_habits,
            interaction.guild_id,
            interaction.user.id,
            interaction.channel_id,
            current,
            scope_value,
            25,
        )
        return [
            app_commands.Choice(
                name=self._habit_choice_label(habit),
                value=str(habit.get("_id") or ""),
            )
            for habit in habits
            if habit.get("_id") is not None
        ]

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("HabitCog cog loaded")

    @habit_group.command(name="add", description="Add a new habit")
    @app_commands.describe(
        habit="Habit name",
        description="Longer description",
        reminder="Daily reminder time",
        destination="Where to track this habit",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def habit(
        self,
        interaction: discord.Interaction,
        habit: str,
        description: Optional[str] = None,
        reminder: Optional[str] = None,
        destination: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        try:
            scope_value, target_channel_id, _ = normalize_habit_target(
                interaction,
                destination,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=True, cause=exc)
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        if not habit.strip():
            raise ValidationError("Habit name cannot be empty.", ephemeral=ephemeral)

        reminder_text = (reminder or "").strip()
        timezone = None
        if reminder_text:

            async def _continue_with_timezone(
                followup_interaction: discord.Interaction,
                resolved_timezone: str,
            ) -> None:
                await self._create_habit(
                    interaction=followup_interaction,
                    habit=habit,
                    description=description,
                    reminder=reminder,
                    ephemeral=ephemeral,
                    timezone=resolved_timezone,
                    scope_value=scope_value,
                    target_channel_id=target_channel_id,
                )

            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/habit add`.",
                response_ephemeral=ephemeral,
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._create_habit(
            interaction=interaction,
            habit=habit,
            description=description,
            reminder=reminder,
            ephemeral=ephemeral,
            timezone=timezone,
            scope_value=scope_value,
            target_channel_id=target_channel_id,
        )

    async def _create_habit(
        self,
        interaction: discord.Interaction,
        habit: str,
        description: Optional[str],
        reminder: Optional[str],
        ephemeral: bool,
        timezone: Optional[str],
        scope_value: str,
        target_channel_id: Optional[int],
    ) -> None:
        document, reminder_time, reminder_failed = await self._persist_habit(
            interaction=interaction,
            habit=habit,
            description=description,
            reminder=reminder,
            ephemeral=ephemeral,
            timezone=timezone,
            scope_value=scope_value,
            target_channel_id=target_channel_id,
        )
        await self._send_created_habit_response(
            interaction,
            document=document,
            reminder_time=reminder_time,
            reminder_failed=reminder_failed,
            ephemeral=ephemeral,
        )

    async def _persist_habit(
        self,
        *,
        interaction: discord.Interaction,
        habit: str,
        description: Optional[str],
        reminder: Optional[str],
        ephemeral: bool,
        timezone: Optional[str],
        scope_value: str,
        target_channel_id: Optional[int],
    ) -> tuple[dict, Optional[object], bool]:
        try:
            document, reminder_time = await asyncio.to_thread(
                HabitFunctions.insert_habit,
                interaction.guild_id,
                interaction.user.id,
                target_channel_id,
                habit,
                description,
                reminder,
                timezone,
                scope_value,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while creating that habit.",
                ephemeral=ephemeral,
                cause=exc,
            )

        reminder_failed = False
        if reminder_time:
            try:
                await asyncio.to_thread(
                    HabitFunctions.insert_habit_task,
                    document,
                    reminder_time,
                    timezone,
                )
            except Exception:
                reminder_failed = True

        return document, reminder_time, reminder_failed

    async def _persist_habit_update(
        self,
        *,
        interaction: discord.Interaction,
        habit_id: str,
        habit: str,
        description: Optional[str],
        reminder: Optional[str],
        ephemeral: bool,
        timezone: Optional[str],
        scope_value: str,
        target_channel_id: Optional[int],
    ) -> tuple[dict, Optional[object], bool]:
        try:
            document, reminder_time = await asyncio.to_thread(
                HabitFunctions.update_habit,
                habit_id,
                interaction.guild_id,
                interaction.user.id,
                target_channel_id,
                habit,
                description,
                reminder,
                timezone,
                scope_value,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while editing that habit.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if document is None:
            raise ValidationError(
                "That habit no longer exists.",
                ephemeral=ephemeral,
            )

        reminder_failed = False
        try:
            await asyncio.to_thread(
                HabitFunctions.sync_habit_tasks,
                document,
                reminder_time,
                timezone,
            )
        except Exception:
            reminder_failed = True

        return document, reminder_time, reminder_failed

    async def _send_created_habit_response(
        self,
        interaction: discord.Interaction,
        *,
        document: dict,
        reminder_time,
        reminder_failed: bool,
        ephemeral: bool,
    ) -> None:
        await self._send_habit_card_response(
            interaction,
            document=document,
            reminder_time=reminder_time,
            reminder_failed=reminder_failed,
            ephemeral=ephemeral,
        )

    async def _send_habit_card_response(
        self,
        interaction: discord.Interaction,
        *,
        document: dict,
        reminder_time,
        reminder_failed: bool,
        ephemeral: bool,
        content: Optional[str] = None,
    ) -> None:
        status = HabitFunctions.today_status(document)
        progress = HabitFunctions.recent_progress(document, days=5)
        payload = HabitEmbeds.habit_item_embed(
            document,
            status,
            progress,
            reminder_time=reminder_time if not reminder_failed else None,
        )
        if content:
            payload["content"] = content
        if reminder_failed:
            reminder_message = "Habit created, but I couldn't schedule the reminder."
            if content:
                payload["content"] = f"{content}\n{reminder_message}"
            else:
                payload["content"] = reminder_message
        payload["view"] = self._build_created_habit_view(
            document,
            ephemeral=ephemeral,
        )

        posted_message = await interaction.followup.send(
            ephemeral=ephemeral,
            wait=True,
            **payload,
        )
        view = payload["view"]
        if isinstance(view, HabitActionView):
            view.message = posted_message

    @habit_group.command(name="list", description="List habits")
    @app_commands.describe(
        status="Filter habits by status",
        sort="Sort order for habits",
        scope="Which habits to include",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Incomplete", value="incomplete"),
            app_commands.Choice(name="Skipped", value="skipped"),
        ],
        sort=[
            app_commands.Choice(name="Ascending", value="ascending"),
            app_commands.Choice(name="Descending", value="descending"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def habits(
        self,
        interaction: discord.Interaction,
        status: Optional[app_commands.Choice[str]] = None,
        sort: Optional[app_commands.Choice[str]] = None,
        scope: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        try:
            scope_value, target_channel_id, scope_label = normalize_habit_list_scope(
                interaction, scope
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=True, cause=exc)
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        status_value = status.value if status else "all"
        sort_value = sort.value if sort else "ascending"
        if scope_value == "channel" and interaction.guild is not None and target_channel_id is not None:
            selected_channel = interaction.guild.get_channel(target_channel_id)
            if isinstance(selected_channel, discord.TextChannel):
                scope_label = f"#{selected_channel.name}"
            else:
                scope_label = f"Channel {target_channel_id}"

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            habits = await asyncio.to_thread(
                HabitFunctions.list_habits,
                interaction.guild_id,
                interaction.user.id,
                target_channel_id,
                status_value,
                scope_value,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while fetching habits.",
                ephemeral=ephemeral,
                cause=exc,
            )

        view = HabitListView(
            habits=habits,
            scope_label=str(scope_label),
            scope_value=scope_value,
            mode=status_value,
            sort=sort_value,
            guild_id=interaction.guild_id,
            channel_id=target_channel_id,
            user_id=interaction.user.id,
            response_ephemeral=ephemeral,
        )
        await view.ensure_session()
        message = await interaction.followup.send(
            ephemeral=ephemeral,
            view=view,
            wait=True,
            **view.payload(),
        )
        view.message = message

    @habit.autocomplete("destination")
    async def habit_create_destination_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return habit_target_autocomplete(interaction, current)

    @habits.autocomplete("scope")
    async def habit_list_scope_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return habit_list_scope_autocomplete(interaction, current)

    @habit_group.command(name="show", description="Show a habit's details")
    @app_commands.describe(
        habit="Habit to show",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def show_habit(
        self,
        interaction: discord.Interaction,
        habit: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = self._default_scope_value(interaction)
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        habit_document = await self._resolve_habit_reference(
            interaction,
            habit,
            scope_value=scope_value,
            ephemeral=ephemeral,
        )
        payload = HabitEmbeds.habit_item_embed(
            habit_document,
            HabitFunctions.today_status(habit_document),
            HabitFunctions.recent_progress(habit_document, days=5),
        )
        payload["view"] = self._build_created_habit_view(
            habit_document,
            ephemeral=ephemeral,
        )
        posted_message = await interaction.followup.send(
            ephemeral=ephemeral,
            wait=True,
            **payload,
        )
        view = payload["view"]
        if isinstance(view, HabitActionView):
            view.message = posted_message

    async def _start_habit_mark_flow(
        self,
        interaction: discord.Interaction,
        *,
        habit: str,
        status_value: str,
        status_label: str,
        date: Optional[str],
        scope_value: str,
        ephemeral: bool,
        locale_code: Optional[str],
    ) -> None:
        timezone = None
        if (date or "").strip():

            async def _continue_with_timezone(
                followup_interaction: discord.Interaction,
                resolved_timezone: str,
            ) -> None:
                await self._run_habit_mark(
                    interaction=followup_interaction,
                    habit=habit,
                    status_value=status_value,
                    status_label=status_label,
                    date=date,
                    scope_value=scope_value,
                    ephemeral=ephemeral,
                    timezone=resolved_timezone,
                    locale_code=locale_code,
                )

            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/habit mark`.",
                response_ephemeral=ephemeral,
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._run_habit_mark(
            interaction=interaction,
            habit=habit,
            status_value=status_value,
            status_label=status_label,
            date=date,
            scope_value=scope_value,
            ephemeral=ephemeral,
            timezone=timezone,
            locale_code=locale_code,
        )

    async def _run_habit_mark(
        self,
        interaction: discord.Interaction,
        *,
        habit: str,
        status_value: str,
        status_label: str,
        date: Optional[str],
        scope_value: str,
        ephemeral: bool,
        timezone: Optional[str],
        locale_code: Optional[str],
    ) -> None:
        habit_document = await self._resolve_habit_reference(
            interaction,
            habit,
            scope_value=scope_value,
            ephemeral=ephemeral,
        )
        habit_id = str(habit_document.get("_id") or "").strip()
        if not habit_id:
            raise ValidationError(
                "That habit is no longer available.",
                ephemeral=ephemeral,
            )

        recorded_at = None
        if (date or "").strip():
            recorded_at = await asyncio.to_thread(
                HabitFunctions.parse_completion_timestamp,
                str(date),
                timezone=timezone,
                locale_code=locale_code,
            )

        updated = await asyncio.to_thread(
            HabitFunctions.add_completion,
            habit_id,
            interaction.guild_id,
            status_value,
            interaction.user.id,
            recorded_at,
        )
        if not updated:
            raise UserVisibleError(
                "That habit could not be updated.",
                ephemeral=ephemeral,
            )

        refreshed_document = await asyncio.to_thread(
            HabitFunctions.fetch_habit,
            habit_id,
            interaction.guild_id,
            interaction.user.id,
        )
        if refreshed_document is None:
            raise UserVisibleError(
                "Updated the habit, but couldn't load the refreshed habit card.",
                ephemeral=ephemeral,
            )

        if recorded_at is None:
            date_label = "today"
        else:
            date_label = recorded_at.date().isoformat()
        confirmation = (
            f"Marked `{refreshed_document.get('name') or 'Habit'}` as "
            f"{status_label} for {date_label}."
        )
        await self._send_habit_card_response(
            interaction,
            document=refreshed_document,
            reminder_time=None,
            reminder_failed=False,
            ephemeral=ephemeral,
            content=confirmation,
        )

    @habit_group.command(
        name="mark",
        description="Record a daily result for a habit",
    )
    @app_commands.describe(
        habit="Habit to mark",
        status="Result to record for the habit",
        date="Optional day to record, for example `yesterday` or `2026-04-18`",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        status=[
            app_commands.Choice(name="Complete", value="complete"),
            app_commands.Choice(name="Skip", value="skip"),
            app_commands.Choice(name="Incomplete", value="incomplete"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def mark_habit(
        self,
        interaction: discord.Interaction,
        habit: str,
        status: Optional[app_commands.Choice[str]] = None,
        date: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = self._default_scope_value(interaction)
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        locale_code = str(getattr(interaction, "locale", "") or "").strip() or None
        status_choice = status or app_commands.Choice(
            name="Complete",
            value="complete",
        )
        await self._start_habit_mark_flow(
            interaction,
            habit=habit,
            status_value=status_choice.value,
            status_label=status_choice.name,
            date=date,
            scope_value=scope_value,
            ephemeral=ephemeral,
            locale_code=locale_code,
        )

    @habit_group.command(name="edit", description="Edit an existing habit")
    @app_commands.describe(
        habit="Habit to edit",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def edit_habit(
        self,
        interaction: discord.Interaction,
        habit: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = self._default_scope_value(interaction)
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        habit_document = await self._resolve_habit_reference(
            interaction,
            habit,
            scope_value=scope_value,
            ephemeral=ephemeral,
        )
        habit_id = str(habit_document.get("_id") or "").strip()
        if not habit_id:
            raise ValidationError(
                "That habit is no longer available.",
                ephemeral=ephemeral,
            )

        reminder_time = await asyncio.to_thread(
            HabitFunctions.get_habit_reminder_time,
            habit_id,
            habit_document.get("guild_id"),
        )
        response_view = self._build_created_habit_view(
            habit_document,
            ephemeral=ephemeral,
        )
        habit_scope = HabitFunctions._normalize_scope(
            str(habit_document.get("scope") or scope_value)
        )
        modal = HabitCreateModal(
            self,
            user_id=interaction.user.id,
            scope_value=habit_scope,
            target_channel_id=habit_document.get("channel_id"),
            response_ephemeral=ephemeral,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            include_scope_select=True,
            title="Edit Habit",
            habit_id=habit_id,
            default_habit=str(habit_document.get("name") or ""),
            default_description=str(habit_document.get("description") or ""),
            default_reminder=(
                reminder_time.strftime("%H:%M") if reminder_time is not None else ""
            ),
            source_view=response_view,
        )
        try:
            await response_view._open_modal(interaction, modal=modal)
        except discord.HTTPException as exc:
            raise UserVisibleError(
                "Something went wrong while opening the edit dialog.",
                ephemeral=ephemeral,
                cause=exc,
            )

    @habit_group.command(name="delete", description="Delete a habit")
    @app_commands.rename(habit_name="habit")
    @app_commands.describe(
        habit_name="Habit to delete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def delete_habit(
        self,
        interaction: discord.Interaction,
        habit_name: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = self._default_scope_value(interaction)
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)
        habit = await self._resolve_habit_reference(
            interaction,
            habit_name,
            scope_value=scope_value,
            ephemeral=ephemeral,
        )

        deleted = await asyncio.to_thread(
            HabitFunctions.delete_habit,
            str(habit.get("_id") or ""),
            interaction.guild_id,
            interaction.user.id,
        )
        if not deleted:
            raise UserVisibleError(
                "That habit could not be deleted.",
                ephemeral=ephemeral,
            )

        deleted_payload = HabitEmbeds.deleted_habit_embed(
            str(habit.get("name") or "Habit")
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **deleted_payload,
        )

    @delete_habit.autocomplete("habit_name")
    async def habit_delete_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self._habit_reference_autocomplete(interaction, current)

    @show_habit.autocomplete("habit")
    async def habit_show_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self._habit_reference_autocomplete(interaction, current)

    @edit_habit.autocomplete("habit")
    async def habit_edit_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self._habit_reference_autocomplete(interaction, current)

    @mark_habit.autocomplete("habit")
    async def habit_mark_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        return await self._habit_reference_autocomplete(interaction, current)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(HabitCog(client))
