import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds.HabitEmbeds import HabitEmbeds
from classes.HabitFunctions import HabitFunctions
from views.HabitActionView import HabitActionView
from views.HabitCreateModal import HabitCreatedActionView
from services.discord_helpers import (
    habit_target_autocomplete,
    normalize_habit_target,
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

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("HabitCog cog loaded")

    @habit_group.command(name="add", description="Create a new habit")
    @app_commands.describe(
        habit="Habit name",
        description="Longer description for this habit",
        reminder="Daily reminder time",
        scope="This channel, another text channel, or personal",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def habit(
        self,
        interaction: discord.Interaction,
        habit: str,
        description: Optional[str] = None,
        reminder: Optional[str] = None,
        scope: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        try:
            scope_value, target_channel_id, _ = normalize_habit_target(interaction, scope)
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
        status = HabitFunctions.today_status(document)
        progress = HabitFunctions.recent_progress(document, days=5)
        payload = HabitEmbeds.habit_item_embed(
            document,
            status,
            progress,
        )
        if reminder_failed:
            payload["content"] = "Habit created, but I couldn't schedule the reminder."
        payload["view"] = HabitCreatedActionView(
            self,
            habit_id=str(document.get("_id") or ""),
            habit_name=str(document.get("name") or "Habit"),
            user_id=int(document.get("user_id") or 0),
            scope_value=HabitFunctions._normalize_scope(
                str(document.get("scope") or "channel")
            ),
            target_channel_id=document.get("channel_id"),
            response_ephemeral=ephemeral,
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
        mode="Show all habits or only incomplete habits",
        scope="This channel, another text channel, or personal",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Incomplete", value="incomplete"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def habits(
        self,
        interaction: discord.Interaction,
        mode: Optional[app_commands.Choice[str]] = None,
        scope: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        try:
            scope_value, target_channel_id, _ = normalize_habit_target(interaction, scope)
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=True, cause=exc)
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        mode_value = mode.value if mode else "incomplete"

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            habits = await asyncio.to_thread(
                HabitFunctions.list_habits,
                interaction.guild_id,
                interaction.user.id,
                target_channel_id,
                mode_value,
                scope_value,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while fetching habits.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not habits:
            await interaction.followup.send(
                ephemeral=ephemeral,
                **HabitEmbeds.habits_empty_embed(mode_value),
            )
            return

        for habit in habits:
            status = HabitFunctions.today_status(habit)
            progress = HabitFunctions.recent_progress(habit, days=5)
            habit_id = str(habit.get("_id") or "")
            habit_name = str(habit.get("name") or "Habit")
            payload = HabitEmbeds.habit_item_embed(habit, status, progress)
            view = HabitActionView(habit_id, habit_name, interaction.user.id)
            await interaction.followup.send(ephemeral=ephemeral, view=view, **payload)

    @habit.autocomplete("scope")
    async def habit_create_scope_autocomplete(
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
        return habit_target_autocomplete(interaction, current)

    @habit_group.command(name="show", description="Show one habit")
    @app_commands.describe(
        habit_name="Habit to show",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def show_habit(
        self,
        interaction: discord.Interaction,
        habit_name: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        del habit_name
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        await interaction.response.send_message(
            "This slash command is not yet implemented.",
            ephemeral=ephemeral,
        )

    @habit_group.command(name="status", description="Set today's status for a habit")
    @app_commands.describe(
        habit_name="Habit to update",
        status="Today's status for the habit",
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
    async def status_habit(
        self,
        interaction: discord.Interaction,
        habit_name: str,
        status: app_commands.Choice[str],
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        del habit_name, status
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        await interaction.response.send_message(
            "This slash command is not yet implemented.",
            ephemeral=ephemeral,
        )

    @habit_group.command(name="edit", description="Edit an existing habit")
    @app_commands.describe(
        habit_name="Habit to edit",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def edit_habit(
        self,
        interaction: discord.Interaction,
        habit_name: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        del habit_name
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        await interaction.response.send_message(
            "This slash command is not yet implemented.",
            ephemeral=ephemeral,
        )

    @habit_group.command(name="delete", description="Delete a habit")
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
        del habit_name
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = self._resolve_response_visibility(
            interaction,
            scope_value,
            visibility,
        )
        await interaction.response.send_message(
            "This slash command is not yet implemented.",
            ephemeral=ephemeral,
        )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(HabitCog(client))
