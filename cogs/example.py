import discord
from discord.ext import commands
import os

import platform

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
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"The bot latency is {round(self.client.latency * 1000)}ms.",
            color=0x42F56C
        )
        await ctx.send(embed=embed)

    @commands.command(aliases=["botinfo"])
    async def info(self, ctx):
        embed = discord.Embed(
            description="Productivity bot",
            color=0x00FF00
        )
        embed.set_author(
            name="About this bot"
        )
        embed.add_field(
            name="Prefix:",
            value=".",
            inline=False
        )
        embed.set_footer(
            text=f"Requested by {ctx.message.author}"
        )
        await ctx.send(embed=embed)

def setup(client):
    client.add_cog(Example(client))