# Color palette
# https://colorswall.com/palette/72717/
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

    """
    There are problems when field project_data['color'] doesn't have color defined
    - add no timer availble
    - stop current timer, if availble and start new one
    """
    @app_commands.command(name="timer", description="toggl get active timer")
    async def timer(self, interaction: discord.Interaction):
        timer_data = self.toggl.getCurrentTimeEntry()
        project_data = self.toggl.getProjectById(timer_data["workspace_id"], timer_data["project_id"])

        if project_data['color'] is None:
            project_data['color'] = "#000000"

        embed = discord.Embed(
            title=":stopwatch: Toggl Current Timer",
            color=discord.Colour.from_str(project_data['color']),
            description=timer_data["description"],
        )
        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        embed.add_field(name="Projekt", value=project_data["name"], inline=False)
        embed.add_field(name="Time passed", value=timer_data["start"], inline=False)

        await interaction.response.send_message(embed=embed)

    """
    1) Check if timer is active
    2) Add stop comfirmation
    """
    @app_commands.command(name="stop", description="toggl stop active time")
    async def stop(self, interaction: discord.Interaction):
        timer_data = self.toggl.getCurrentTimeEntry()

        # Already stopped timer
        if timer_data is None:
            description = "No timer running"
        # Timer to be stopped
        else:
            description = "Timer stopped"

        embed = discord.Embed(
            title=":stopwatch: Toggl Stop Timer",
            color=discord.Colour.from_str("#552d4f"),
            description=description
        )

        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        if timer_data is not None:
            project_data = self.toggl.getProjectById(timer_data["workspace_id"], timer_data["project_id"])
            timer_stop = self.toggl.stopCurrentTimeEntry()
            embed.add_field(name="Projekt", value=project_data["name"], inline=False)
            # This field causes chrashes
            # by passing timer_data[]
            # embed.add_field(name="Time passed", value=timer_data["start"], inline=False)

        await interaction.response.send_message(embed=embed)

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