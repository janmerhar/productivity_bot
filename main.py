# https://www.youtube.com/watch?v=-D2CvmHTqbE
import logging.handlers
import logging
import discord
import asyncio
from discord.ext import commands
from discord import app_commands

from config import env

tick_disabled = env.get("TICK_DISABLED") == "true"

intents = discord.Intents.default()
intents.message_content = True
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


@bot.event
async def on_ready():
    print("Online")


async def load():
    extensions = [
        "cogs.AliasCog",
        "cogs.Example",
        "cogs.ExampleCog",
        "cogs.TogglCog",
    ]

    if not tick_disabled:
        extensions.append("cogs.TickTickCog")

    for extension in extensions:
        await bot.load_extension(extension)


async def main():
    await load()
    await bot.start(env["DISCORD_TOKEN"])


asyncio.run(main())
