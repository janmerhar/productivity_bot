# https://www.youtube.com/watch?v=-D2CvmHTqbE
import logging.handlers
import logging
import discord
import asyncio
from typing import Optional
from discord.ext import commands

from config import env

tick_disabled = env.get("TICK_DISABLED") == "true"
sync_guild_id = env.get("GUILD_ID")

intents = discord.Intents.default()
# intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

logger = logging.getLogger("discord")
logger.setLevel(logging.DEBUG)
logging.getLogger("discord.http").setLevel(logging.WARNING)

file_handler = logging.handlers.RotatingFileHandler(
    filename="discord.log",
    encoding="utf-8",
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    backupCount=5,  # Rotate through 5 files
)
dt_fmt = "%Y-%m-%d %H:%M:%S"
formatter = logging.Formatter(
    "[{asctime}] [{levelname:<8}] {name}: {message}", dt_fmt, style="{"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

discord.utils.setup_logging(formatter=formatter)

_sync_done = False


@bot.event
async def on_ready():
    global _sync_done
    if not _sync_done:
        guild_object = discord.Object(id=sync_guild_id) if sync_guild_id else None
        try:
            bot.tree.clear_commands(guild=None)
            await bot.tree.sync(guild=None)
            if guild_object is not None:
                await bot.tree.sync(guild=guild_object)
        except Exception:
            logging.getLogger(__name__).exception("Failed to sync application commands")
        else:
            _sync_done = True
            logging.getLogger(__name__).info(
                "Synced application commands%s.",
                f" for guild {sync_guild_id}" if guild_object is not None else "",
            )

    print("Online")


async def load():
    extensions = [
        "cogs.AliasCog",
        "cogs.DailyTaskCog",
        "cogs.TogglCog",
        "cogs.CryptoCog",
        "cogs.StocksCog",
    ]

    if not tick_disabled:
        extensions.append("cogs.TickTickCog")

    for extension in extensions:
        await bot.load_extension(extension)


async def main():
    await load()
    await bot.start(env["DISCORD_TOKEN"])


asyncio.run(main())
