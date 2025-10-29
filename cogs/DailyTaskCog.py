import asyncio
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

import dateparser
from classes.DailyJob import OneTimeSchedule2
from classes.DailyJobManager import DailyJobManager
from config.env import env


def parse_time_string(raw: str) -> Optional[datetime.datetime]:
    text = raw.strip()
    if not text:
        return None

    now = datetime.datetime.now()

    dt = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DAY_OF_MONTH": "current",
        },
    )

    if dt is not None:
        dt = dt.replace(second=0, microsecond=0)
        if dt <= now:
            dt += datetime.timedelta(days=1)
        return dt

    return None


class DailyTaskCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
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
        scheduled_dt = parse_time_string(time)
        if scheduled_dt is None:
            await interaction.response.send_message(
                "I couldn't understand that time. Try '08:30', '8pm', or similar.",
                ephemeral=True,
            )
            return

        job_schedule = OneTimeSchedule2(datetime=scheduled_dt.isoformat())
        payload = message.strip()
        job_type = "message"
        job_data = {"message": message}
        confirmation_time = scheduled_dt.strftime("%H:%M")
        confirmation = f"Got it! I'll post here every day at {confirmation_time}."

        if payload.lower().startswith("stock:"):
            tickers = [
                token.strip().upper()
                for token in payload[6:].split(",")
                if token.strip()
            ]
            if not tickers:
                await interaction.response.send_message(
                    "Please provide at least one stock ticker after `stock:`.",
                    ephemeral=True,
                )
                return

            job_type = "stock"
            job_data = {"tickers": tickers}
            quoted = ", ".join(f"`{ticker}`" for ticker in tickers)
            confirmation = (
                f"Got it! I'll post daily stock prices for {quoted} at "
                f"{confirmation_time}."
            )

        await interaction.response.defer(ephemeral=True)
        manager = DailyJobManager()
        try:
            await asyncio.to_thread(
                manager.insert_job,
                interaction.channel_id,
                job_type,
                job_data,
                job_schedule,
            )
        except Exception:
            await interaction.followup.send(
                "Something went wrong while scheduling that task. Please try again.",
                ephemeral=True,
            )
            return
        await interaction.followup.send(confirmation, ephemeral=True)

    @tasks.loop(minutes=1)
    async def _runner(self) -> None:
        manager = DailyJobManager()
        manager.get_due_jobs()
        runs = await asyncio.to_thread(manager.run_due_jobs)

        print("RUN DUE JOBS:", runs)
        if not runs:
            return

        for job, payload in runs:
            if not payload:
                continue

            channel = self.bot.get_channel(job.channel_id)
            if channel is None:
                channel = await self.bot.fetch_channel(job.channel_id)

            await channel.send(**payload)

    @_runner.before_loop
    async def _before_runner(self) -> None:
        await self.bot.wait_until_ready()


async def setup(client: commands.Bot) -> None:
    await client.add_cog(DailyTaskCog(client), guilds=[discord.Object(env["GUILD_ID"])])
