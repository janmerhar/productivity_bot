import datetime
from dataclasses import dataclass
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks


@dataclass
class DailyJob:
    channel_id: int
    hour: int
    minute: int
    message: str
    last_run: Optional[datetime.date] = None


class DailyTaskCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.jobs: List[DailyJob] = []
        self._runner.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print("DailyTaskCog cog loaded")

    def cog_unload(self) -> None:
        if self._runner.is_running():
            self._runner.cancel()

    @app_commands.command(
        name="dailytask", description="Send a message every day at the given time"
    )
    async def daily_task(
        self, interaction: discord.Interaction, time: str, message: str
    ) -> None:
        hour_str, minute_str = time.split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
        if not 0 <= hour < 24 or not 0 <= minute < 60:
            await interaction.response.send_message(
                "Please provide time as HH:MM in 24-hour format.",
                ephemeral=True,
            )
            return

        job = DailyJob(
            channel_id=interaction.channel_id,
            hour=hour,
            minute=minute,
            message=message,
        )
        self.jobs.append(job)
        await interaction.response.send_message(
            f"Got it! I'll post here every day at {hour:02d}:{minute:02d}.",
            ephemeral=True,
        )

    @tasks.loop(minutes=1)
    async def _runner(self) -> None:
        if not self.jobs:
            return

        now = datetime.datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        today = now.date()

        for job in self.jobs:
            if (
                job.hour == current_hour
                and job.minute == current_minute
                and job.last_run != today
            ):
                channel = self.bot.get_channel(job.channel_id)
                if channel is None:
                    channel = await self.bot.fetch_channel(job.channel_id)
                await channel.send(job.message)
                job.last_run = today

    @_runner.before_loop
    async def _before_runner(self) -> None:
        await self.bot.wait_until_ready()


async def setup(client: commands.Bot) -> None:
    await client.add_cog(
        DailyTaskCog(client), guilds=[discord.Object(id=864242668066177044)]
    )
