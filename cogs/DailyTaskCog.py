import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands, tasks

import dateparser

from classes.CryptoFunctions import CryptoFunctions
from cogs.CryptoEmbeds import CryptoEmbeds
from config import env


def parse_time_string(raw: str) -> Optional[Tuple[int, int]]:
    text = raw.strip()
    if not text:
        return None

    dt = dateparser.parse(
        text,
        settings={
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DAY_OF_MONTH": "current",
        },
    )

    if text is not None:
        return dt.hour, dt.minute

    for fmt in ("%H:%M", "%H%M", "%I:%M%p", "%I%p", "%H"):
        try:
            dt = datetime.datetime.strptime(text, fmt)
            return dt.hour, dt.minute
        except ValueError:
            continue

    return None


@dataclass
class DailyJob:
    channel_id: int
    hour: int
    minute: int
    type: str
    data: dict
    last_run: Optional[datetime.date] = None


CRYPTO_CHANNEL_ID = 1429530996000161938
CRYPTO_TICKERS = ["bitcoin", "ethereum", "syrup"]
CRYPTO_CURRENCY = "usd"
CRYPTO_CHANGE_PERIODS = ("24h", "7d", "30d")
CRYPTO_HEADER = "Daily crypto prices"

CRYPTO_DAILY_JOB = DailyJob(
    channel_id=CRYPTO_CHANNEL_ID,
    hour=8,
    minute=0,
    type="crypto",
    data={"tickers": CRYPTO_TICKERS},
)


class DailyTaskCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.jobs: List[DailyJob] = []
        self.jobs.append(CRYPTO_DAILY_JOB)
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
        parsed = parse_time_string(time)
        if parsed is None:
            await interaction.response.send_message(
                "I couldn't understand that time. Try '08:30', '8pm', or similar.",
                ephemeral=True,
            )
            return

        hour, minute = parsed

        job = DailyJob(
            channel_id=interaction.channel_id,
            hour=hour,
            minute=minute,
            type="message",
            data={"message": message},
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
                if job.type == "crypto":
                    await self._send_crypto_embeds(
                        channel, job.data.get("tickers", CRYPTO_TICKERS)
                    )
                else:
                    await channel.send(job.data.get("message", ""))
                job.last_run = today

    @_runner.before_loop
    async def _before_runner(self) -> None:
        await self.bot.wait_until_ready()

    async def _send_crypto_embeds(self, channel, tickers: List[str]) -> None:
        try:
            rows = CryptoFunctions.fetchPrices(
                tickers,
                CRYPTO_CURRENCY,
                CRYPTO_CHANGE_PERIODS,
            )
        except Exception as exc:
            await channel.send(f"Failed to fetch crypto prices: {exc}")
            return

        if not rows:
            await channel.send("No crypto price data returned today.")
            return

        embeds = []
        for coin in rows:
            embed_kwargs = CryptoEmbeds.price_embed(coin, CRYPTO_CURRENCY)
            embed = embed_kwargs.get("embed")
            if embed is not None:
                embeds.append(embed)

        if not embeds:
            await channel.send("No crypto price data returned today.")
            return

        await channel.send(content=CRYPTO_HEADER, embeds=embeds[:10])


async def setup(client: commands.Bot) -> None:
    await client.add_cog(DailyTaskCog(client), guilds=[discord.Object(env["GUILD_ID"])])
