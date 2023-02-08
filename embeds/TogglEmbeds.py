from re import A
from typing import Dict, Optional
import discord
from discord.ext import commands
from discord import app_commands
import inspect

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

    def timer_embed(self):
        timer_data = self.toggl.getCurrentTimeEntry()

        if timer_data is not None:
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

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Current Timer",
                color=discord.Colour.from_str("#df80c7"),
                description="No active timer",
            )
            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            return {"embeds": [embed]}

    """
    - Add check if project color is not defined
    """

    def start_embed(self, project: str = None, description: str = None) -> dict:
        workspace_id = self.toggl.aboutMe()["default_workspace_id"]
        curr_timer = self.toggl.getCurrentTimeEntry()

        embeds = []

        if curr_timer is not None:
            timer_stopped_embed = self.stop_embed()

            embeds.append(timer_stopped_embed["embed"])

        print(project)
        if project is not None:
            project_data = self.toggl.getProject(identifier=project)

            new_time = self.toggl.startCurrentTimeEntry(
                workspace_id, description=description, pid=project_data["id"] if project_data is not None else None,)
        else:
            new_time = self.toggl.startCurrentTimeEntry(
                workspace_id, description=description)

        embed = discord.Embed(
            title=":stopwatch: Toggl Start Timer",
            # color=discord.Colour.from_str(
            #     project_data["color"] if project is not None and project_data is not None else "#df80c7"
            # ),
        )
        embed.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        if project is not None and project_data is not None:
            embed.add_field(
                name="Project ID", value=project_data["id"], inline=False)
            embed.add_field(
                name="Project name", value=project_data["name"], inline=False)

        embed.add_field(
            name="Timer description", value=new_time["description"], inline=False)
        embed.add_field(
            name="Timer start", value=new_time["start"], inline=False)

        embeds.append(embed)

        return {"embeds": embeds}

    """
    - Stops the timer but does not send embed back
    """

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

    """
    - Add project color of embed, if applicable
    """

    def savetimer_embed(self, command: str, workspace_id: int = None, billable: str = None, description: str = None,
                        pid: int = None, tags: str = None, tid: int = None,):

        inserted_id = self.toggl.saveTimer(
            command=command, workspace_id=workspace_id, billable=billable, description=description, project=pid, tid=tid)

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

        return {"embeds": [embed]}

    def removetimer_embed(self, identifier: str):
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

            return {"embeds": [embed]}
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

            return {"embeds": [embed]}

    """
    - TogglFunctions.py/startSavedTimer does not start timer given by Id
    - Active timer will be stopped regardless if the saved command exist in database
    """

    def startsaved_embed(self, identifier: str):
        embeds = []

        active_timer = self.toggl.getCurrentTimeEntry()

        if active_timer is not None:
            stopped_embed = self.stop_embed()

            embeds.append(stopped_embed["embed"])

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

            return {"embeds": [embed]}
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

            embeds.append(embed)

            return {"embeds": embeds}

    def populartimers_embed(self, n: int):
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

        return {"embeds": [embed]}

    """
    - Function is configured for only this days' timerrs to be displayed,
    otherwise it fails
    """

    def timerhistory_embed(self, n: int) -> dict:
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

        return {"embeds": [embed]}

    #
    # Projects
    #

    """
    - Add more arguments to be passed in slash command
        -> workspace_id, name, active=True, auto_estimates=None, billable=None,
                      color=None, currency="EUR", estimated_hours=1, is_private=None, template=None 
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

    #
    # Shortcuts
    #

    def getFunctionByName(self, name):
        try:
            fn = getattr(self, f"{name}_embed")
            return fn
        except:
            return None

    def getDefaultArgs(func):
        signature = inspect.signature(func)

        return {
            k: v.default
            for k, v in signature.parameters.items()
            if v.default is not inspect.Parameter.empty
        }

    def createalias_embed(self, command: str,  alias: str, arguments: str = "", cog_param: object = {}) -> dict:
        print("enter embed")
        alias_fn = self.getFunctionByName(name=command)

        if alias_fn is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl New Shortcut",
                color=discord.Colour.from_str("#552d4f"),
                description="Slash command not found"
            )
            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            return {"embeds": [embed]}
        else:
            insert_args = self.toggl.parseShortcutArguments(arguments)
            cog_param.update(insert_args)

            inserted_data = self.toggl.saveShortcut2(
                command=command, alias=alias, param=cog_param)

            embed = discord.Embed(
                title=":stopwatch: Toggl New Shortcut",
                color=discord.Colour.from_str("#552d4f"),
            )
            embed.set_thumbnail(
                url="https://i.imgur.com/Cmjl4Kb.png"
            )

            embed.add_field(name="Alias",
                            value=inserted_data["alias"], inline=False)
            embed.add_field(name="Command",
                            value=inserted_data["command"], inline=False)
            embed.add_field(name="Application",
                            value=inserted_data["application"], inline=False)
            embed.add_field(name="Id",
                            value=str(inserted_data["_id"]), inline=False)

            for key, value in inserted_data["param"].items():
                embed.add_field(name=f"Param __{str(key)}__",
                                value=str(value), inline=False)

            return {"embeds": [embed]}

    """
    - Default parameters are problematic
    - Add number_of_runs increment after each run
        -> creating function inside togglEmbeds might be useful
    """

    def usealias_embed(self, alias: str):
        alias_data = self.toggl.findSavedShortcut(alias=alias)

        embed_no_found = discord.Embed(
            title=":stopwatch: Toggl New Shortcut",
            color=discord.Colour.from_str("#552d4f"),
            description="Alias command not found"
        )
        embed_no_found.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        if alias_data is None:
            return {"embeds": [embed_no_found]}

        fn_embed = self.getFunctionByName(alias_data["command"])

        if fn_embed is None:
            embed_no_found.description = "Alias command not correct"

            return {"embeds": [embed_no_found]}

        # print(alias_data)
        embed = fn_embed(**alias_data["param"])

        # print(embed)
        return embed


if __name__ == "__main__":
    embeds = TogglEmbeds()
