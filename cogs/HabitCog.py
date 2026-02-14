import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds.HabitEmbeds import HabitEmbeds
from classes.HabitFunctions import HabitFunctions
from views.HabitActionView import HabitActionView
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


class HabitCog(commands.Cog):
    habit_group = app_commands.Group(name="habit", description="Manage habits")

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("HabitCog cog loaded")

    @habit_group.command(name="create", description="Create a new habit")
    @app_commands.describe(
        name="Habit name",
        description="Longer description for this habit",
        reminder="Daily reminder time",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def habit(
        self,
        interaction: discord.Interaction,
        name: str,
        description: Optional[str] = None,
        reminder: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        if not name.strip():
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
                    name=name,
                    description=description,
                    reminder=reminder,
                    ephemeral=ephemeral,
                    timezone=resolved_timezone,
                )

            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/habit create`.",
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._create_habit(
            interaction=interaction,
            name=name,
            description=description,
            reminder=reminder,
            ephemeral=ephemeral,
            timezone=timezone,
        )

    async def _create_habit(
        self,
        interaction: discord.Interaction,
        name: str,
        description: Optional[str],
        reminder: Optional[str],
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        try:
            document, reminder_time = await asyncio.to_thread(
                HabitFunctions.insert_habit,
                interaction.guild_id,
                interaction.user.id,
                interaction.channel_id,
                name,
                description,
                reminder,
                timezone,
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

        payload = HabitEmbeds.insert_habit_embed(
            name=document["name"],
            description=document.get("description"),
            reminder_time=reminder_time,
        )
        if reminder_failed:
            payload["content"] = "Habit created, but I couldn't schedule the reminder."

        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @habit_group.command(name="list", description="List habits")
    @app_commands.describe(
        mode="Show all habits or only incomplete habits",
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
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        mode_value = mode.value if mode else "incomplete"

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            habits = await asyncio.to_thread(
                HabitFunctions.list_habits,
                interaction.guild_id,
                interaction.user.id,
                interaction.channel_id,
                mode_value,
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


async def setup(client: commands.Bot) -> None:
    await client.add_cog(HabitCog(client))


