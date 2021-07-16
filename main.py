import discord
from discord.ext import commands
import os

client = commands.Bot(command_prefix = ".")

@client.event
async def on_ready():
    print("Bot is ready.")

client.run("ODY1NTUyMjI0ODI1MjQ1Njk3.YPFqUw.rOrPem7DDCrbTV2CPr_wind0Ec8")