import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds.HabitEmbeds import HabitEmbeds
from classes.HabitFunctions import HabitFunctions
from views.HabitActionView import HabitActionView
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
            await interaction.response.send_message(
                ephemeral=ephemeral,
                content="Habit name cannot be empty.",
            )
            return

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            document, reminder_time = await asyncio.to_thread(
                HabitFunctions.insert_habit,
                interaction.guild_id,
                interaction.user.id,
                interaction.channel_id,
                name,
                description,
                reminder,
            )
        except ValueError as exc:
            await interaction.followup.send(ephemeral=ephemeral, content=str(exc))
            return
        except Exception:
            await interaction.followup.send(
                ephemeral=ephemeral,
                content="Something went wrong while creating that habit.",
            )
            return

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
        except Exception:
            await interaction.followup.send(
                ephemeral=ephemeral,
                content="Something went wrong while fetching habits.",
            )
            return

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
