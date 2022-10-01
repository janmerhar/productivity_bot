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