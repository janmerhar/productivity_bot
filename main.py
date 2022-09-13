# https://www.youtube.com/watch?v=-D2CvmHTqbE
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