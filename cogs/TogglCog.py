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

    """
    There are problems when field project_data['color'] doesn't have color defined
    - add no timer availble
    - stop current timer, if availble and start new one
    - error when timer hahs no project_id
    """
    @app_commands.command(name="timer", description="toggl get active timer")
    async def timer(self, interaction: discord.Interaction):
        timer_data = self.toggl.getCurrentTimeEntry()
        project_data = self.toggl.getProjectById(
            workspace_id=timer_data["workspace_id"], project_id=timer_data["project_id"])

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

        embed.add_field(
            name="Projekt", value=project_data["name"], inline=False)
        embed.add_field(name="Time passed",
                        value=timer_data["start"], inline=False)

        await interaction.response.send_message(embed=embed)

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
        inserted_id = self.toggl.saveTimer(
            command=command, workspace_id=workspace_id, billable=billable, description=description, pid=pid, tid=tid)

        timer = self.toggl.findSavedTimer(inserted_id)

        embed = discord.Embed(
            title=":stopwatch: Toggl Insert Timer",
            color=discord.Colour.from_str("#552d4f"),
        )

        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        embed.add_field(
            name="Timer command", value=timer["command"], inline=False)
        embed.add_field(
            name="Project ID", value=timer['param']["pid"], inline=False)
        embed.add_field(
            name="Timer description", value=timer['param']["description"], inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="removetimer", description="toggl remove saved timer")
    async def removetimer(self, interaction: discord.Interaction, identifier: str):
        timer = self.toggl.findSavedTimer(identifier)

        if timer is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Delete Timer",
                color=discord.Colour.from_str("#552d4f"),
                description="Timer not found"
            )

            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            await interaction.response.send_message(embed=embed)
        else:
            self.toggl.removeSavedTimer(identifier)

            embed = discord.Embed(
                title=":stopwatch: Toggl Delete Timer",
                color=discord.Colour.from_str("#552d4f"),
                description=f"Timer {timer['command']} deleted"
            )

            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            embed.add_field(
                name="Timer command", value=timer["command"], inline=False)
            embed.add_field(
                name="Project ID", value=timer['param']["pid"], inline=False)
            embed.add_field(
                name="Timer description", value=timer['param']["description"], inline=False)
            await interaction.response.send_message(embed=embed)

    """
    - TogglFunctions.py/startSavedTimer does not start timer given by Id
    - When force stopped, the timer duration is incorrect
    """
    @app_commands.command(name="startsaved", description="toggl start saved timer")
    async def startsaved(self, interaction: discord.Interaction, identifier: str):
        timer = self.toggl.startSavedTimer(identifier)

        if timer is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Start Saved Timer",
                color=discord.Colour.from_str("#552d4f"),
                description="Timer not found"
            )
            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )
            await interaction.response.send_message(embed=embed)
        else:
            project = self.toggl.getProjectById(
                workspace_id=timer["workspace_id"], project_id=timer["pid"])

            embed = discord.Embed(
                title=":stopwatch: Toggl Start Saved Timer",
                color=discord.Colour.from_str(project['color']),
            )
            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            embed.add_field(
                name="Project ID", value=timer["pid"], inline=False)
            embed.add_field(
                name="Project name", value=project["name"], inline=False)
            embed.add_field(
                name="Timer description", value=timer["description"], inline=False)

            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="populartimers", description="toggl most popular timers")
    async def populartimers(self, interaction: discord.Interaction, n: int = 5):
        timers = self.toggl.mostCommonlyUsedTimers(n)

        embed = discord.Embed(
            title=":stopwatch: Toggl Stop Timer",
            color=discord.Colour.from_str("#552d4f"),
            description=f"{len(timers)} most commonly used timers"
        )

        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        for timer in timers:
            embed.add_field(
                name="Command", value=timer["command"], inline=True
            )
            embed.add_field(
                name="Project ID", value=timer["param"]["pid"], inline=True
            )
            embed.add_field(
                name="Description", value=timer["param"]["description"], inline=True
            )

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="timerhistory", description="toggl get timer history")
    async def timerhistory(self, interaction: discord.Interaction, n: int):
        history = self.toggl.getLastNTimeEntryHistory(n)

        embed = discord.Embed(
            title=":stopwatch: Toggl Timer History",
            color=discord.Colour.from_str("#552d4f"),
            description=f"Last {n} timers"
        )

        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        for timer in history:
            project_data = self.toggl.getProjectById(
                workspace_id=timer["workspace_id"], project_id=timer["project_id"])

            project = project_data["name"] if project_data["name"] is not None else "<no project name>"
            name = timer["description"] if len(
                timer["description"]) > 0 else "<no description>"
            duration = f"{timer['duration'] // 60} minutes"

            embed.add_field(name="Project", value=project, inline=True)
            embed.add_field(name="Name", value=name, inline=True)
            embed.add_field(name="Duration", value=duration, inline=True)

        await interaction.response.send_message(embed=embed)

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
