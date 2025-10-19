import datetime
from typing import Optional

import discord
from discord.ext import commands, tasks
from zoneinfo import ZoneInfo

from config import env

RUN_AT = datetime.time(hour=8, tzinfo=ZoneInfo("Europe/Ljubljana"))
MESSAGE = "Test message at 8 am"
CHANNEL_ID = "1429530996000161938"


class DailyCronExample(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        if CHANNEL_ID:
            self.daily_job.start()

    def cog_unload(self) -> None:
        if self.daily_job.is_running():
            self.daily_job.cancel()

    @tasks.loop(time=RUN_AT)
    async def daily_job(self) -> None:
        if not CHANNEL_ID:
            return
        channel = self.client.get_channel(CHANNEL_ID)
        if channel is None:
            channel = await self.client.fetch_channel(CHANNEL_ID)
        await channel.send(MESSAGE)

    @daily_job.before_loop
    async def before_daily_job(self) -> None:
        await self.client.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(DailyCronExample(bot))
