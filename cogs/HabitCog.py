import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from embeds.HabitEmbeds import HabitEmbeds
from classes.HabitFunctions import HabitFunctions
from views.HabitActionView import HabitActionView


class HabitCog(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("HabitCog cog loaded")

    @app_commands.command(name="habit", description="Create a new habit")
    @app_commands.describe(
        name="Habit name",
        description="Longer description for this habit",
        reminder="Daily reminder time",
    )
    async def habit(
        self,
        interaction: discord.Interaction,
        name: str,
        description: Optional[str] = None,
        reminder: Optional[str] = None,
    ) -> None:
        if not name.strip():
            await interaction.response.send_message(
                ephemeral=True,
                content="Habit name cannot be empty.",
            )
            return

        await interaction.response.defer(ephemeral=True)

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
            await interaction.followup.send(ephemeral=True, content=str(exc))
            return
        except Exception:
            await interaction.followup.send(
                ephemeral=True,
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

        await interaction.followup.send(ephemeral=True, **payload)

    @app_commands.command(name="habits", description="List habits")
    @app_commands.describe(mode="Show all habits or only incomplete habits")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Incomplete", value="incomplete"),
        ]
    )
    async def habits(
        self,
        interaction: discord.Interaction,
        mode: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        mode_value = mode.value if mode else "incomplete"

        await interaction.response.defer(ephemeral=True)

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
                ephemeral=True,
                content="Something went wrong while fetching habits.",
            )
            return

        if not habits:
            await interaction.followup.send(
                ephemeral=True,
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
            await interaction.followup.send(ephemeral=True, view=view, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(HabitCog(client))
