import discord
from discord.ext import commands
import os

class Example(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print("Bot is ready to rumble")
    
    # Commands
    @commands.command()
    async def ping(self, ctx):
        await ctx.send(f"Pong! {round (self.client.latency * 1000)}ms")

def setup(client):
    client.add_cog(Example(client))