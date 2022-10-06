# Color palette
# https://colorswall.com/palette/72717/
from embeds.TogglEmbeds import TogglEmbeds
import discord
from discord.ext import commands
from discord import app_commands

import json
import os
import platform
import random
import sys
import aiohttp

from classes.TogglFunctions import TogglFunctions
from dotenv import dotenv_values
env = dotenv_values(".env")


class TogglCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.toggl = TogglFunctions(env["TOGGL_TOKEN"])
        self.embeds = TogglEmbeds()

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
        param = self.embeds.aboutme_embed()

        await interaction.response.send_message(**param)

    #
    # Tracking
    #
    @app_commands.command(name="start", description="toggl start timer")
    async def start(self, interaction: discord.Interaction, project_id: int, description: str = None):
        param = self.embeds.start_embed(
            project_id=project_id, description=description)

        await interaction.response.send_message(**param)

    @app_commands.command(name="timer", description="toggl get active timer")
    async def timer(self, interaction: discord.Interaction):
        param = self.embeds.timer_embed()
        await interaction.response.send_message(**param)

    @app_commands.command(name="stop", description="toggl stop active time")
    async def stop(self, interaction: discord.Interaction):
        param = self.embeds.stop_embed()

        await interaction.response.send_message(**param)

    @app_commands.command(name="inserttimer", description="toggl insert past time")
    async def inserttimer(self, interaction: discord.Interaction):
        pass

    #
    # Saved timers
    # mongoDB
    #

    """
    - Improve tags handling
    """
    @app_commands.command(name="savetimer", description="toggl save timer")
    async def savetimer(self, interaction: discord.Interaction, command: str, workspace_id: int = None, billable: str = None, description: str = None,
                        pid: int = None, tags: str = None, tid: int = None,):
        param = self.embeds.savetimer_embed(command=command, workspace_id=workspace_id, billable=billable, description=description, 
                                            pid=pid, tags=tags)

        await interaction.response.send_message(**param)

    @app_commands.command(name="removetimer", description="toggl remove saved timer")
    async def removetimer(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.removetimer_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    @app_commands.command(name="startsaved", description="toggl start saved timer")
    async def startsaved(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.startsaved_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    @app_commands.command(name="populartimers", description="toggl most popular timers")
    async def populartimers(self, interaction: discord.Interaction, n: int = 5):
        param = self.embeds.populartimers_embed(n=n)

        await interaction.response.send_message(**param)

    @app_commands.command(name="timerhistory", description="toggl get timer history")
    async def timerhistory(self, interaction: discord.Interaction, n: int):
        param = self.embeds.timerhistory_embed(n=n)

        await interaction.response.send_message(**param)

    #
    # Projects
    #
    @app_commands.command(name="newproject", description="toggl create new project")
    async def newproject(self, interaction: discord.Interaction, name: str):
        param = self.embeds.newproject_embed(name=name)

        await interaction.response.send_message(**param)

    @app_commands.command(name="workspaceprojects", description="toggl get all projects")
    async def workspaceprojects(self, interaction: discord.Interaction):
        param = self.embeds.workspaceprojects_embed()

        await interaction.response.send_message(**param)

    @app_commands.command(name="getproject", description="toggl get project by id")
    async def getproject(self, interaction: discord.Interaction, project_id: int):
        param = self.embeds.getproject_embeds(project_id=project_id)

        await interaction.response.send_message(**param)


async def setup(client):
    await client.add_cog(TogglCog(client), guilds=[discord.Object(id=864242668066177044)])
