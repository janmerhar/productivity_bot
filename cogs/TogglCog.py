import discord
from discord.ext import commands
from discord import app_commands

import json
import os
import platform
import random
import sys
import aiohttp

from Classes.TogglFunctions import TogglFunctions
from dotenv import dotenv_values
env = dotenv_values(".env")

class TogglCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.toggl = TogglFunctions(env["TOGGL_TOKEN"])

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print("TogglCog cog loaded")

    # Commands

    # 
    # Authentication
    # 
    @app_commands.command(name="aboutme", description="toggl about me")
    async def aboutme(self, interaction: discord.Interaction):
        data = self.toggl.aboutMe()

        embed = discord.Embed(
            title=":stopwatch: Toggl About Me",
            color=0xdf80c7
        )
        embed.set_thumbnail(
            url="https://assets.track.toggl.com/images/profile.png"
        )

        embed.add_field(name="ID", value=data["id"], inline=False)
        embed.add_field(name="Email", value=data["email"], inline=False)
        embed.add_field(name="Full name", value=data["fullname"], inline=False)

        embed.add_field(name="Timezone", value=data["timezone"], inline=False)
        embed.add_field(name="Registration date", value=data["created_at"], inline=False)
        embed.add_field(name="Default workspace ID", value=data["default_workspace_id"], inline=False)
        
        await interaction.response.send_message(embed=embed)

    # 
    # Tracking
    # 
    @app_commands.command(name="start", description="toggl start timer")
    async def start(self, interaction: discord.Interaction):
        pass

    @app_commands.command(name="timer", description="toggl get active timer")
    async def timer(self, interaction: discord.Interaction):
        pass

    @app_commands.command(name="stop", description="toggl stop active time")
    async def stop(self, interaction: discord.Interaction):
        pass

    @app_commands.command(name="inserttime", description="toggl insert past time")
    async def inserttimer(self, interaction: discord.Interaction):
        pass


    @app_commands.command(name="timerhistory", description="toggl get timer history")
    async def timerhistory(self, interaction: discord.Interaction):
        pass

    @app_commands.command(name="timers", description="toggl get last n timers' history")
    async def timers(self, interaction: discord.Interaction):
        pass

    # 
    # Workspace
    # 
    # @app_commands.command(name="", description="")
    # async def (self, interaction: discord.Interaction):
        # pass

    # 
    # Projects
    # 
    # @app_commands.command(name="", description="")
    # async def (self, interaction: discord.Interaction):
        # pass

async def setup(client):
    await client.add_cog(TogglCog(client), guilds=[discord.Object(id=864242668066177044)])