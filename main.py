# https://www.youtube.com/watch?v=-D2CvmHTqbE
import logging.handlers
import logging
import discord
import asyncio
from discord.ext import commands
from discord import app_commands
import os

from dotenv import dotenv_values
env = dotenv_values(".env")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

logger = logging.getLogger('discord')
logger.setLevel(logging.DEBUG)
logging.getLogger('discord.http').setLevel(logging.WARNING)

handler = logging.handlers.RotatingFileHandler(
    filename='discord.log',
    encoding='utf-8',
    maxBytes=32 * 1024 * 1024,  # 32 MiB
    backupCount=5,  # Rotate through 5 files
)
dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter(
    '[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)

discord.utils.setup_logging(handler=handler, formatter=formatter)


@bot.event
async def on_ready():
    print("Online")


async def load():
    for file in os.listdir("./cogs"):
        if file.endswith(".py"):
            await bot.load_extension(f"cogs.{file[:-3]}")


async def main():
    await load()
    await bot.start(env["DISCORD_TOKEN"])

asyncio.run(main())
