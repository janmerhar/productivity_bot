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
import inspect

from Classes.TogglFunctions import TogglFunctions
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
    @app_commands.command(name="aboutme", description="Toggl about me")
    async def aboutme(self, interaction: discord.Interaction):
        param = self.embeds.aboutme_embed()

        await interaction.response.send_message(**param)

    #
    # Tracking
    #
    @app_commands.command(name="start", description="Toggl start timer")
    @app_commands.describe(
        project="Project that timer will start in",
        description="Description of this timer",
    )
    async def start(self, interaction: discord.Interaction, project: str = None, description: str = None):
        param = self.embeds.start_embed(
            project=project, description=description)

        await interaction.response.send_message(**param)

    @app_commands.command(name="timer", description="Toggl get active timer")
    async def timer(self, interaction: discord.Interaction):
        param = self.embeds.timer_embed()
        await interaction.response.send_message(**param)

    @app_commands.command(name="stop", description="Toggl stop active time")
    async def stop(self, interaction: discord.Interaction):
        param = self.embeds.stop_embed()

        await interaction.response.send_message(**param)

    @app_commands.command(name="inserttimer", description="Toggl insert past time")
    async def inserttimer(self, interaction: discord.Interaction):
        pass

    #
    # Saved timers
    # mongoDB
    #

    """
    - Improve tags handling
    """
    @app_commands.command(name="savetimer", description="Toggl save timer")
    @app_commands.describe(
        command="Name of the saved timer",
        workspace_id="Workspace id",
        billable="Billable",
        description="Description of the saved timer",
        pid="Project id",
        tags="Tags, separated by whitespaces",
        tid="Tid"
    )
    async def savetimer(self, interaction: discord.Interaction, command: str, workspace_id: int = None, billable: str = None, description: str = None,
                        pid: int = None, tags: str = None, tid: int = None,):
        param = self.embeds.savetimer_embed(command=command, workspace_id=workspace_id, billable=billable, description=description,
                                            pid=pid, tags=tags)

        await interaction.response.send_message(**param)

    @app_commands.command(name="removetimer", description="Toggl remove saved timer")
    @app_commands.describe(
        identifier="Timer to be removed"
    )
    async def removetimer(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.removetimer_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    @app_commands.command(name="startsaved", description="Toggl start saved timer")
    @app_commands.describe(
        identifier="Saved timer to start"
    )
    async def startsaved(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.startsaved_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    @startsaved.autocomplete("identifier")
    async def starsaved_autocomplete(self, interaction: discord.Interaction, current: str = ""):
        options = self.embeds.startsaved_autocomplete_embed(current=current)

        return options

    @app_commands.command(name="populartimers", description="Toggl most popular timers")
    @app_commands.describe(
        n="Number of most popular timers to be displayed"
    )
    async def populartimers(self, interaction: discord.Interaction, n: int = 5):
        param = self.embeds.populartimers_embed(n=n)

        await interaction.response.send_message(**param)

    @app_commands.command(name="timerhistory", description="Toggl get timer history")
    @app_commands.describe(
        n="Number of timers to display"
    )
    async def timerhistory(self, interaction: discord.Interaction, n: int):
        param = self.embeds.timerhistory_embed(n=n)

        await interaction.response.send_message(**param)

    #
    # Projects
    #
    @app_commands.command(name="newproject", description="Toggl create new project")
    @app_commands.describe(
        name="Name of newly created project"
    )
    async def newproject(self, interaction: discord.Interaction, name: str):
        param = self.embeds.newproject_embed(name=name)

        await interaction.response.send_message(**param)

    @app_commands.command(name="workspaceprojects", description="Toggl get all projects")
    async def workspaceprojects(self, interaction: discord.Interaction):
        param = self.embeds.workspaceprojects_embed()

        await interaction.response.send_message(**param)

    @app_commands.command(name="getproject", description="Toggl get project by id")
    @app_commands.describe(
        project_id="Project id"
    )
    async def getproject(self, interaction: discord.Interaction, project_id: int):
        param = self.embeds.getproject_embed(project_id=project_id)

        await interaction.response.send_message(**param)

    #
    # Shortcuts
    #


    def getFunctionByName(self, name):
        try:
            fn = getattr(self, f"{name}")
            return fn
        except:
            return None

    def getDefaultParameters(self, cog_fn):
        return {
            param.name: param.default
            for param in cog_fn.parameters
            if param.default is not None and type(param.default) != discord.utils._MissingSentinel
        }

    """
    @app_commands.command(name="createalias", description="create alias")
    @app_commands.describe(
        command="Command name",
        alias="Alias for the command",
        arguments="Semicolon separated arguments"
    )
    async def createalias(self, interaction: discord.Interaction, command: str,  alias: str, arguments: str = ""):
        cog_fn = self.getFunctionByName(name=command)
        cog_param = self.getDefaultParameters(cog_fn=cog_fn)

        param = self.embeds.createalias_embed(
            command=command, alias=alias, arguments=arguments, cog_param=cog_param)

        await interaction.response.send_message(**param)

    @app_commands.command(name="usealias", description="use alias")
    @app_commands.describe(
        alias="Alias of a command to be used",
    )
    async def usealias(self, interaction: discord.Interaction, alias: str):
        param = self.embeds.usealias_embed(alias=alias)

        await interaction.response.send_message(**param)


async def setup(client):
    await client.add_cog(TogglCog(client), guilds=[discord.Object(id=864242668066177044)])
