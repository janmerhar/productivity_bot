from typing import Dict
import discord
from discord.ext import commands
from discord import app_commands

from classes.TogglFunctions import TogglFunctions
from dotenv import dotenv_values
env = dotenv_values(".env")


class TogglEmbeds:
    def __init__(self):
        self.toggl = TogglFunctions(env["TOGGL_TOKEN"])

    #
    # Authentication
    #

    def aboutme_embed(self) -> dict:
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

        return {"embed": embed}

    #
    # Tracking
    #

    """
    - Add stop embed if another timer is active
    - Add search for project using name
    """

    def start_embed(self, project_id: int, description: str = None) -> dict[str, list[discord.Embed]]:
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

        return {"embeds": [embed]}

    def stop_embed(self) -> dict:
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
                workspace_id=timer_data["workspace_id"], project_id=timer_data["project_id"])
            timer_stop = self.toggl.stopCurrentTimeEntry()
            embed.add_field(
                name="Projekt", value=project_data["name"], inline=False)
            # This field causes chrashes
            # by passing timer_data[]
            # embed.add_field(name="Time passed", value=timer_data["start"], inline=False)

        return {"embed": embed}

    #
    # Saved timers
    # mongoDB
    #

    #
    # Projects
    #

    """
    - Add more arguments to be passed in slash command
    """

    def newproject_embed(self, name: str) -> dict:
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

        return {"embeds": [embed]}

    """
    WHEN LOOPING OVER RECEIVED PROJECTS
    THE LAST ONE IS NOT FULLY WIRTTEN IN EMBED
    """

    def workspaceprojects_embed(self):
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

        return {"embeds": [embed]}

    def getproject_embeds(self, project_id: int) -> dict:
        workspace_id = self.toggl.aboutMe()["default_workspace_id"]
        project = self.toggl.getProjectById(
            workspace_id=workspace_id, project_id=project_id)

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

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Timer History",
                color=discord.Colour.from_str("#552d4f"),
                description="No project was found"
            )

            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            return {"embeds": [embed]}
