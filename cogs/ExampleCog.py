import discord
from discord.ext import commands
import json
import os
import platform
import random
import sys
import aiohttp
from discord import app_commands

class Example(commands.Cog):
    def __init__(self, client):
        self.client = client
    
    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print("Example cog loaded")
    
    # Commands
    @app_commands.command(name="ping", description="sends a ping")
    async def ping(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🏓 Pong!",
            description=f"The bot latency is {round(self.client.latency * 1000)}ms.",
            color=0x42F56C
        )
        await interaction.response.send_message(f"PONG!!!")

    @app_commands.command(name="botinfo", description="serves bot info")
    async def info(self, interaction: discord.Interaction):
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
        # embed.set_footer(
            # text=f"Requested by {ctx.message.author}"
        # )
        # await ctx.send(embed=embed)
        await interaction.response.send_message(f"BOTINFOOOo")

    # NOT WORKING
    @app_commands.command(name="serverinfo", description="serves server info")
    async def serverinfo(self, interaction: discord.Interaction):
        """
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
        """
        await interaction.response.send_message(f"SERVERINFOOOo")
    
    @app_commands.command(name="bitcoin", description="serves bitcoin info")
    async def bitcoin(self, interaction: discord.Interaction):
        """
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
        """
        await interaction.response.send_message(f"BITCOININFOOOo")

    @app_commands.command(name="calendar", description="shows your calendar")
    async def calendar(self, interaction: discord.Interaction):
        """
        server = ctx.message.guild
        time = str(server.created_at)
        time = time.split(" ")
        time = time[0]

        embed = discord.Embed(
            title=":calendar: Google Calendar",
            description="Embed discription",
            color=0x4086f4
        )
        embed.set_thumbnail(
            url="https://ssl.gstatic.com/calendar/images/dynamiclogo_2020q4/calendar_17_2x.png"
        )

        # non inline field
        embed.add_field(name="non inline name", value="non inline value", inline=False)
        # inline field values
        # maximum 3 inline fields per row
        embed.add_field(name="INLINE NAME1", value="INLINE VALUE1", inline=True)
        embed.add_field(name="INLINE NAME2", value="INLINE VALUE2", inline=True)
        embed.add_field(name="INLINE NAME3", value="INLINE VALUE3", inline=True)
        embed.add_field(name="INLINE NAME4", value="INLINE VALUE4", inline=True)

        embed.set_footer(
            text=f"Footer"
        )

        # adding reactions on message
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("💖")
        await msg.add_reaction("🇦")
        await msg.add_reaction("🇧")
        await msg.add_reaction("🇨")
        await msg.add_reaction("🇩")
        await msg.add_reaction("🇪")
        """
        await interaction.response.send_message(f"calendar!!!")

async def setup(client):
    await client.add_cog(Example(client), guilds=[discord.Object(id=864242668066177044)])