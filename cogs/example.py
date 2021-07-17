import discord
from discord.ext import commands
import os

import json
import os
import platform
import random
import sys
import aiohttp

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

    @commands.command(name="serverinfo")
    async def serverinfo(self, ctx):
        server = ctx.message.guild
        roles = [x.name for x in server.roles]
        role_length = len(roles)
        if role_length > 50:
            roles = roles[:50]
            roles.append(f">>>> Displaying[50/{len(roles)}] Roles")
        roles = ", ".join(roles)
        channels = len(server.channels)
        time = str(server.created_at)
        time = time.split(" ")
        time = time[0]

        embed = discord.Embed(
            title="Name:",
            description=server,
            color=0x00FF00
        )
        embed.set_thumbnail(
            url=server.icon_url
        )
        embed.add_field(
            name=f"Roles ({role_length})\n",
            value=roles
        )
        embed.set_footer(
            text=f"Created at: {time}"
        )
        await ctx.send(embed=embed)
    
    @commands.command(aliases=["btc"])
    async def bitcoin(self, ctx):
        url = "https://api.coindesk.com/v1/bpi/currentprice/BTC.json"

        async with aiohttp.ClientSession() as session:
            raw_response = await session.get(url)
            response = await raw_response.text()
            response = json.loads(response)
            embed = discord.Embed(
                title="Bitcoin price:",
                description=f"{response['bpi']['USD']['rate']} $",
                color=0xf2a900
            )
            await ctx.send(embed=embed)

def setup(client):
    client.add_cog(Example(client))