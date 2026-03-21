from re import A
from typing import Dict, Optional
import discord
from discord.ext import commands
from discord import app_commands
from classes.UserSettingsFunctions import UserSettingsFunctions
from classes.TogglFunctions import TogglFunctions
from abstract.EmbedsAbstract import EmbedsAbstract


class TogglEmbeds(EmbedsAbstract):
    @staticmethod
    def _get_toggl(guild_id: int, user_id: int) -> Optional[TogglFunctions]:
        if guild_id is None or user_id is None:
            return None
        api_key = UserSettingsFunctions.get_toggl_api_key(user_id)
        if not api_key:
            return None
        return TogglFunctions(api_key)

    @staticmethod
    def _missing_key_embed() -> dict:
        embed = discord.Embed(
            title=":stopwatch: Toggl",
            color=discord.Colour.from_str("#552d4f"),
            description="Run any Toggl command and provide your API key in the popup.",
        )
        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
        return {"embeds": [embed]}

    @staticmethod
    def _get_function_by_name(name: str):
        if not name:
            return None
        cleaned = " ".join(str(name).strip().lower().split())
        if cleaned.startswith("toggl "):
            cleaned = cleaned[len("toggl ") :].strip()
        alias_map = {
            "about": "aboutme",
            "key clear": "togglkeyclear",
            "timer start": "start",
            "timer stop": "stop",
            "timer current": "timer",
            "timer insert": "inserttimer",
            "timer history": "timerhistory",
            "saved create": "savetimer",
            "saved delete": "removetimer",
            "saved start": "startsaved",
            "saved popular": "populartimers",
            "project create": "newproject",
            "project list": "workspaceprojects",
            "project get": "getproject",
            "alias create": "createalias",
        }
        if cleaned in alias_map:
            cleaned = alias_map[cleaned]
        elif " " in cleaned:
            return None
        try:
            return getattr(TogglEmbeds, f"{cleaned}_embed")
        except AttributeError:
            return None

    #
    # Authentication
    #

    @staticmethod
    def aboutme_embed(guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        data = toggl.aboutMe()

        embed = discord.Embed(title=":stopwatch: Toggl About Me", color=0xDF80C7)
        embed.set_thumbnail(url="https://assets.track.toggl.com/images/profile.png")

        embed.add_field(name="ID", value=data["id"], inline=False)
        embed.add_field(name="Email", value=data["email"], inline=False)
        embed.add_field(name="Full name", value=data["fullname"], inline=False)

        embed.add_field(name="Timezone", value=data["timezone"], inline=False)
        embed.add_field(
            name="Registration date", value=data["created_at"], inline=False
        )
        embed.add_field(
            name="Default workspace ID",
            value=data["default_workspace_id"],
            inline=False,
        )

        return {"embed": embed}

    #
    # Tracking
    #

    @staticmethod
    def timer_embed(guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timer_data = toggl.getCurrentTimeEntry()

        if timer_data is not None:
            project_data = toggl.getProjectById(
                workspace_id=timer_data["workspace_id"],
                project_id=timer_data["project_id"],
            )

            if project_data["color"] is None:
                project_data["color"] = "#000000"

            embed = discord.Embed(
                title=":stopwatch: Toggl Current Timer",
                color=discord.Colour.from_str(project_data["color"]),
                description=timer_data["description"],
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            embed.add_field(name="Projekt", value=project_data["name"], inline=False)
            embed.add_field(name="Time passed", value=timer_data["start"], inline=False)

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Current Timer",
                color=discord.Colour.from_str("#df80c7"),
                description="No active timer",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}

    """
    - Add check if project color is not defined
    """

    @staticmethod
    def start_embed(
        guild_id: int,
        user_id: int,
        project: str = None,
        description: str = None,
    ) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        workspace_id = toggl.aboutMe()["default_workspace_id"]
        curr_timer = toggl.getCurrentTimeEntry()

        embeds = []

        if curr_timer is not None:
            timer_stopped_embed = TogglEmbeds.stop_embed(guild_id, user_id)

            embeds.append(timer_stopped_embed["embed"])

        print(project)
        if project is not None:
            project_data = toggl.getProject(
                identifier=project,
                workspace_id=workspace_id,
            )

            new_time = toggl.startCurrentTimeEntry(
                workspace_id,
                description=description,
                pid=project_data["id"] if project_data is not None else None,
            )
        else:
            new_time = toggl.startCurrentTimeEntry(
                workspace_id, description=description
            )

        embed = discord.Embed(
            title=":stopwatch: Toggl Start Timer",
            # color=discord.Colour.from_str(
            #     project_data["color"] if project is not None and project_data is not None else "#df80c7"
            # ),
        )
        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        if project is not None and project_data is not None:
            embed.add_field(name="Project ID", value=project_data["id"], inline=False)
            embed.add_field(
                name="Project name", value=project_data["name"], inline=False
            )

        embed.add_field(
            name="Timer description", value=new_time["description"], inline=False
        )
        embed.add_field(name="Timer start", value=new_time["start"], inline=False)

        embeds.append(embed)

        return {"embeds": embeds}

    """
    - Stops the timer but does not send embed back
    """

    @staticmethod
    def stop_embed(guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timer_data = toggl.getCurrentTimeEntry()

        # Already stopped timer
        if timer_data is None:
            description = "No timer running"
        # Timer to be stopped
        else:
            description = "Timer stopped"

        embed = discord.Embed(
            title=":stopwatch: Toggl Stop Timer",
            color=discord.Colour.from_str("#552d4f"),
            description=description,
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        if timer_data is not None:
            project_data = toggl.getProjectById(
                workspace_id=timer_data["workspace_id"],
                project_id=timer_data["project_id"],
            )
            timer_stop = toggl.stopCurrentTimeEntry()
            embed.add_field(name="Projekt", value=project_data["name"], inline=False)
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

    @staticmethod
    def savetimer_embed(
        guild_id: int,
        user_id: int,
        command: str,
        workspace_id: int = None,
        billable: str = None,
        description: str = None,
        pid: int = None,
        tags: str = None,
        tid: int = None,
    ):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()

        inserted_id = toggl.saveTimer(
            guild_id=guild_id,
            user_id=user_id,
            command=command,
            workspace_id=workspace_id,
            billable=billable,
            description=description,
            project=pid,
            tid=tid,
        )

        timer = toggl.findSavedTimer(inserted_id, guild_id, user_id)

        embed = discord.Embed(
            title=":stopwatch: Toggl Insert Timer",
            color=discord.Colour.from_str("#552d4f"),
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        embed.add_field(name="Timer command", value=timer["command"], inline=False)
        embed.add_field(name="Project ID", value=timer["param"]["pid"], inline=False)
        embed.add_field(
            name="Timer description", value=timer["param"]["description"], inline=False
        )

        return {"embeds": [embed]}

    @staticmethod
    def removetimer_embed(identifier: str, guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timer = toggl.findSavedTimer(identifier, guild_id, user_id)

        if timer is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Delete Timer",
                color=discord.Colour.from_str("#552d4f"),
                description="Timer not found",
            )

            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}
        else:
            toggl.removeSavedTimer(identifier, guild_id, user_id)

            embed = discord.Embed(
                title=":stopwatch: Toggl Delete Timer",
                color=discord.Colour.from_str("#552d4f"),
                description=f"Timer {timer['command']} deleted",
            )

            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            embed.add_field(name="Timer command", value=timer["command"], inline=False)
            embed.add_field(
                name="Project ID", value=timer["param"]["pid"], inline=False
            )
            embed.add_field(
                name="Timer description",
                value=timer["param"]["description"],
                inline=False,
            )

            return {"embeds": [embed]}

    """
    - TogglFunctions.py/startSavedTimer does not start timer given by Id
    - Active timer will be stopped regardless if the saved command exist in database
    """

    @staticmethod
    def startsaved_embed(identifier: str, guild_id: int, user_id: int):
        embeds = []
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()

        active_timer = toggl.getCurrentTimeEntry()

        if active_timer is not None:
            stopped_embed = TogglEmbeds.stop_embed(guild_id, user_id)

            embeds.append(stopped_embed["embed"])

        timer = toggl.startSavedTimer(identifier, guild_id, user_id)

        if timer is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Start Saved Timer",
                color=discord.Colour.from_str("#552d4f"),
                description="Timer not found",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}
        else:
            project = toggl.getProjectById(
                workspace_id=timer["workspace_id"], project_id=timer["pid"]
            )

            embed = discord.Embed(
                title=":stopwatch: Toggl Start Saved Timer",
                color=discord.Colour.from_str(project["color"]),
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            embed.add_field(name="Project ID", value=timer["pid"], inline=False)
            embed.add_field(name="Project name", value=project["name"], inline=False)
            embed.add_field(
                name="Timer description", value=timer["description"], inline=False
            )

            embeds.append(embed)

            return {"embeds": embeds}

    @staticmethod
    def startsaved_autocomplete_embed(
        current: str,
        guild_id: int,
        user_id: int,
    ):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return []
        res = [
            app_commands.Choice(name=timer["command"], value=timer["command"])
            for timer in toggl.findSavedTimersLike(
                current,
                guild_id,
                user_id,
            )
        ]

        return res

    @staticmethod
    def populartimers_embed(n: int, guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        timers = toggl.mostCommonlyUsedTimers(n, guild_id, user_id)

        embed = discord.Embed(
            title=":stopwatch: Toggl Stop Timer",
            color=discord.Colour.from_str("#552d4f"),
            description=f"{len(timers)} most commonly used timers",
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        for timer in timers:
            embed.add_field(name="Command", value=timer["command"], inline=True)
            embed.add_field(name="Project ID", value=timer["param"]["pid"], inline=True)
            embed.add_field(
                name="Description", value=timer["param"]["description"], inline=True
            )

        return {"embeds": [embed]}

    """
    - Function is configured for only this days' timerrs to be displayed,
    otherwise it fails
    """

    @staticmethod
    def timerhistory_embed(n: int, guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        history = toggl.getLastNTimeEntryHistory(n)

        embed = discord.Embed(
            title=":stopwatch: Toggl Timer History",
            color=discord.Colour.from_str("#552d4f"),
            description=f"Last {n} timers",
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        for timer in history:
            project_data = toggl.getProjectById(
                workspace_id=timer["workspace_id"], project_id=timer["project_id"]
            )

            project = (
                project_data["name"]
                if project_data["name"] is not None
                else "<no project name>"
            )
            name = (
                timer["description"]
                if len(timer["description"]) > 0
                else "<no description>"
            )
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

    @staticmethod
    def newproject_embed(name: str, guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        project = toggl.createProject(
            toggl.aboutMe()["default_workspace_id"], name=name
        )

        if type(project) != str:
            embed = discord.Embed(
                title=":stopwatch: Toggl Create Project Details", description=name
            )

            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
            embed.add_field(name="Project ID", value=project["id"], inline=True)
            embed.add_field(name="Workspace ID", value=project["wid"], inline=True)
            embed.add_field(name="Creation date", value=project["at"], inline=False)
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Create Project Details",
                description=f"Project {name} already exists",
            )

            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        return {"embeds": [embed]}

    """
    WHEN LOOPING OVER RECEIVED PROJECTS
    THE LAST ONE IS NOT FULLY WIRTTEN IN EMBED
    """

    @staticmethod
    def workspaceprojects_embed(guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        projects = toggl.getProjectsByWorkspace(toggl.aboutMe()["default_workspace_id"])

        embed = discord.Embed(
            title=":stopwatch: Toggl All Projects",
            color=discord.Colour.from_str("#552d4f"),
        )

        embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

        for project in projects:
            embed.add_field(name="Project ID", value=project["id"], inline=True)
            embed.add_field(name="Project name", value=project["name"], inline=True)
            embed.add_field(
                name="Hours documented", value=project["actual_hours"], inline=True
            )

        return {"embeds": [embed]}

    @staticmethod
    def getproject_embed(project: str, guild_id: int, user_id: int) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        workspace_id = toggl.aboutMe()["default_workspace_id"]
        project_data = toggl.getProject(project, workspace_id=workspace_id)

        if project_data is not None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Project Details",
                color=discord.Colour.from_str(project_data["color"] or "#552d4f"),
                description=project_data["name"],
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            embed.add_field(name="Project ID", value=project_data["id"], inline=True)
            embed.add_field(name="Workspace ID", value=workspace_id, inline=True)
            embed.add_field(
                name="Creation date", value=project_data["created_at"], inline=False
            )
            embed.add_field(
                name="Hours documented",
                value=project_data["actual_hours"],
                inline=False,
            )

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":stopwatch: Toggl Timer History",
                color=discord.Colour.from_str("#552d4f"),
                description="No project was found",
            )

            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}

    @staticmethod
    def project_autocomplete_embed(
        current: str,
        guild_id: int,
        user_id: int,
    ) -> list[app_commands.Choice[str]]:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return []

        projects = toggl.findProjectsLike(
            identifier=current,
            workspace_id=toggl.workspace_id,
            limit=25,
        )

        choices: list[app_commands.Choice[str]] = []
        for project in projects:
            project_id = project.get("id")
            if project_id is None:
                continue

            project_name = str(project.get("name") or "").strip() or "Unnamed project"
            label = f"{project_name} | #{project_id}"
            choices.append(
                app_commands.Choice(
                    name=label[:100],
                    value=str(project_id),
                )
            )

        return choices

    #
    # Shortcuts
    #

    @staticmethod
    def createalias_embed(
        guild_id: int,
        user_id: int,
        command: str,
        alias: str,
        arguments: str = "",
        cog_param: object = {},
    ) -> dict:
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        alias_fn = TogglEmbeds._get_function_by_name(command)

        if alias_fn is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl New Shortcut",
                color=discord.Colour.from_str("#552d4f"),
                description="Slash command not found",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            return {"embeds": [embed]}
        else:
            insert_args = toggl.parseShortcutArguments(arguments)
            cog_param.update(insert_args)

            inserted_data = toggl.saveShortcut2(
                guild_id=guild_id,
                user_id=user_id,
                command=command,
                alias=alias,
                param=cog_param,
            )

            embed = discord.Embed(
                title=":stopwatch: Toggl New Shortcut",
                color=discord.Colour.from_str("#552d4f"),
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")

            embed.add_field(name="Alias", value=inserted_data["alias"], inline=False)
            embed.add_field(
                name="Command", value=inserted_data["command"], inline=False
            )
            embed.add_field(
                name="Application", value=inserted_data["application"], inline=False
            )
            embed.add_field(name="Id", value=str(inserted_data["_id"]), inline=False)

            for key, value in inserted_data["param"].items():
                embed.add_field(
                    name=f"Param __{str(key)}__", value=str(value), inline=False
                )

            return {"embeds": [embed]}

    """
    - Add number_of_runs increment after each run
        -> creating function inside togglEmbeds might be useful
    - Add argument for passing alias_data as querying will not be needed with AliasCog.py implementation
    """

    @staticmethod
    def usealias_embed(alias: str, guild_id: int, user_id: int):
        toggl = TogglEmbeds._get_toggl(guild_id, user_id)
        if toggl is None:
            return TogglEmbeds._missing_key_embed()
        alias_data = toggl.findSavedShortcut(alias, guild_id, user_id)
        if alias_data is None:
            embed = discord.Embed(
                title=":stopwatch: Toggl Shortcut",
                color=discord.Colour.from_str("#552d4f"),
                description="Alias not found",
            )
            embed.set_thumbnail(url="https://i.imgur.com/Cmjl4Kb.png")
            return {"embeds": [embed]}

        fn_embed = TogglEmbeds._get_function_by_name(alias_data["command"])
        params = dict(alias_data.get("param") or {})
        params["guild_id"] = guild_id
        params["user_id"] = user_id
        embed = fn_embed(**params)

        return embed


if __name__ == "__main__":
    embeds = TogglEmbeds()
