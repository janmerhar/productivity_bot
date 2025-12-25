import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.PomodoroFunctions import PomodoroFunctions
from embeds.PomodoroEmbeds import PomodoroEmbeds
from config.env import env


class PomodoroCog(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("PomodoroCog cog loaded")

    @app_commands.command(name="pomodoro", description="Start a pomodoro timer")
    @app_commands.describe(
        mode="Pick focus or break",
        duration="Duration in minutes (optional)",
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Focus", value="focus"),
            app_commands.Choice(name="Break", value="break"),
        ]
    )
    async def pomodoro(
        self,
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
        duration: Optional[int] = None,
    ) -> None:
        if duration is not None and duration <= 0:
            await interaction.response.send_message(
                ephemeral=True, content="Duration must be greater than zero."
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            end_time, resolved_duration = await asyncio.to_thread(
                PomodoroFunctions.insert_timer,
                interaction.channel_id,
                mode.value,
                duration,
                interaction.user.id,
            )
        except Exception:
            await interaction.followup.send(
                ephemeral=True,
                content="Something went wrong while starting that pomodoro.",
            )
            return

        await interaction.followup.send(
            ephemeral=True,
            **PomodoroEmbeds.insert_timer_embed(
                mode.value,
                resolved_duration,
                end_time,
            ),
        )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(PomodoroCog(client), guilds=[discord.Object(env["GUILD_ID"])])
