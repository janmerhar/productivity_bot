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

from classes.TogglFunctions import TogglFunctions
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
        embed.add_field(name="Registration date",
                        value=data["created_at"], inline=False)
        embed.add_field(name="Default workspace ID",
                        value=data["default_workspace_id"], inline=False)

        await interaction.response.send_message(embed=embed)

    #
    # Tracking
    #
    """
    MAYBE WOULD BE NICE TO HAVE A WAY OF TELLING USER THAT PREVIOUS TIMER HAS BEEN AUTO STOPPED
    """
    @app_commands.command(name="start", description="toggl start timer")
    async def start(self, interaction: discord.Interaction, project_id: int, description: str = None):
        workspace_id = self.toggl.aboutMe()["default_workspace_id"]
        curr_timer = self.toggl.getCurrentTimeEntry()

        # if curr_timer is not None:
        # await self.stop(interaction)

        new_time = self.toggl.startCurrentTimeEntry(
            workspace_id, description=description, pid=project_id,)

        project = self.toggl.getProjectById(
            workspace_id=workspace_id, project_id=project_id)

        embed = discord.Embed(
            title=":stopwatch: Toggl Start Timer",
            color=discord.Colour.from_str(project["color"]),
        )
        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        embed.add_field(
            name="Project ID", value=project["id"], inline=False)
        embed.add_field(
            name="Project name", value=project["name"], inline=False)
        embed.add_field(
            name="Timer description", value=new_time["description"], inline=False)
        embed.add_field(
            name="Timer start", value=new_time["start"], inline=False)

        await interaction.response.send_message(embed=embed)

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
            timer_data["workspace_id"], timer_data["project_id"])

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
            project_data = self.toggl.getProjectById(
                timer_data["workspace_id"], timer_data["project_id"])
            timer_stop = self.toggl.stopCurrentTimeEntry()
            embed.add_field(
                name="Projekt", value=project_data["name"], inline=False)
            # This field causes chrashes
            # by passing timer_data[]
            # embed.add_field(name="Time passed", value=timer_data["start"], inline=False)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="inserttimer", description="toggl insert past time")
    async def inserttimer(self, interaction: discord.Interaction):
        pass

    #
    # Saved timers
    # mongoDB
    #

    @app_commands.command(name="savetimer", description="toggl save timer")
    async def savetimer(self, interaction: discord.Interaction):
        pass

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
                timer["workspace_id"], timer["pid"])

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

    """
    FOR NOW THE MAXIMUM VALUE OF N IS __5__
    OTHERWISE BOT DOES NOT RESPOND
    - I suspect that Discord's servers timeout the bot, since it takes too long time
    """
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
                timer["workspace_id"], timer["project_id"])

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
        project = self.toggl.createProject(
            self.toggl.aboutMe()["default_workspace_id"], name=name)

        if type(project) != str:
            embed = discord.Embed(
                title=":stopwatch: Toggl Create Project Details",
                description=name
            )

            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )
            embed.add_field(name="Project ID",
                            value=project["id"], inline=True)
            embed.add_field(name="Workspace ID",
                            value=project["wid"], inline=True)
            embed.add_field(name="Creation date",
                            value=project["at"], inline=False)
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Create Project Details",
                description=f"Project {name} already exists"
            )

            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

        await interaction.response.send_message(embed=embed)

    """
    WHEN LOOPING OVER RECEIVED PROJECTS
    THE LAST ONE IS NOT FULLY WIRTTEN IN EMBED
    """
    @app_commands.command(name="workspaceprojects", description="toggl get all projects")
    async def workspaceprojects(self, interaction: discord.Interaction):
        projects = self.toggl.getProjectsByWorkspace(
            self.toggl.aboutMe()["default_workspace_id"])

        embed = discord.Embed(
            title=":stopwatch: Toggl All Projects",
            color=discord.Colour.from_str("#552d4f"),
        )

        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        for project in projects:
            embed.add_field(name="Project ID",
                            value=project["id"], inline=True)
            embed.add_field(name="Project name",
                            value=project["name"], inline=True)
            embed.add_field(name="Hours documented",
                            value=project["actual_hours"], inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="getproject", description="toggl get project by id")
    async def getproject(self, interaction: discord.Interaction, project_id: int):
        workspace_id = self.toggl.aboutMe()["default_workspace_id"]
        project = self.toggl.getProjectById(workspace_id, project_id)

        if project != "Resource can not be found":
            embed = discord.Embed(
                title=":stopwatch: Toggl Project Details",
                color=discord.Colour.from_str(project["color"]),
                description=project["name"]
            )
            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            embed.add_field(name="Project ID",
                            value=project["id"], inline=True)
            embed.add_field(name="Workspace ID",
                            value=workspace_id, inline=True)
            embed.add_field(name="Creation date",
                            value=project["created_at"], inline=False)
            embed.add_field(name="Hours documented",
                            value=project["actual_hours"], inline=False)

            await interaction.response.send_message(embed=embed)
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Timer History",
                color=discord.Colour.from_str("#552d4f"),
                description="No project was found"
            )

            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            await interaction.response.send_message(embed=embed)


async def setup(client):
    await client.add_cog(TogglCog(client), guilds=[discord.Object(id=864242668066177044)])
