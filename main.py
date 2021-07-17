import discord
from discord.ext import commands
import os

client = commands.Bot(command_prefix = ".")

# Nalganje cogs-ov
@client.command()
async def load(ctx, extension):
    client.load_extension(f"cogs.{extension}")

@client.command()
async def unload(ctx, extension):
    client.unload_extension(f"cogs.{extension}")

for filename in os.listdir("./cogs"):
    if filename.endswith(".py"):
        client.load_extension(f"cogs.{filename[:-3]}")

@client.command()
async def clear(ctx, ammount=5):
    await ctx.channel.purge(limit=ammount)

client.run("ODY1NTUyMjI0ODI1MjQ1Njk3.YPFqUw.rOrPem7DDCrbTV2CPr_wind0Ec8")