from re import A
from typing import Dict, Optional
import discord
from discord.ext import commands
from discord import app_commands
import inspect

from Classes.TickTickFunctions import TickTickFunctions
from abstract.EmbedsAbstract import EmbedsAbstract  # Se moram implemenetirati

from dotenv import dotenv_values
env = dotenv_values(".env")


class TickTickEmbeds(EmbedsAbstract):
    def __init__(self):
        self.ticktick = TickTickFunctions(
            env["TICK_EMAIL"], env["TICK_PASSWORD"], env["TICK_ID"], env["TICK_SECRET"], env["TICK_URI"])

    #
    # Tasks
    #

    def newtask_embed(self, name: str, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        project_id = self.ticktick.getProject(project_id)

        if project_id == {} or project_id is None:
            project_id = None
        else:
            project_id = project_id["id"]

        task = self.ticktick.createTask(
            title=name, projectId=project_id, content=content, desc=desc, timeZone=time_zone, reminders=reminders, repeat=repeat,
            priority=priority, sortOrder=sort_order, items=items,
            # startDate=start_date, endDate=end_date, -- vidva hoceta tip parametra date
        )
        project = self.ticktick.getProjectById(task["projectId"])

        embed = discord.Embed(
            title=":ballot_box_with_check: TickTick New Task",
            color=discord.Colour.from_str(
                project["color"] if project != {} else "#ffb301")
        )

        embed.set_thumbnail(
            url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
        )

        embed.add_field(
            name="Task ID", value=task["id"], inline=True)
        embed.add_field(
            name="Task title", value=task["title"], inline=True)
        if project != {}:
            embed.add_field(
                name="List name", value=project["name"], inline=True)
        embed.add_field(
            name="Task reminders", value=f"{len(task['reminders'])} reminders", inline=True)
        embed.add_field(
            name="Task subtasks", value=f"{len(task['items'])} reminders", inline=False)

        return {"embeds": [embed]}

    def newsubtask_embed(self, name: str, parent: str, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        parent_data = self.ticktick.getTask(parent)

        if parent_data is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick New Task",
                color="#ffb301",
                description="Parent not found"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            task = self.ticktick.createTask(
                title=name, projectId=parent_data["projectId"], content=content, desc=desc, timeZone=time_zone, reminders=reminders, repeat=repeat,
                priority=priority, sortOrder=sort_order, items=items,
                # startDate=start_date, endDate=end_date, -- vidva hoceta tip parametra date
            )

            self.ticktick.createSubtask(task, parent_data["id"])

            project = self.ticktick.getProjectById(task["projectId"])

            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick New Task",
                color=discord.Colour.from_str(
                    project["color"] if project != {} else "#ffb301")
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            embed.add_field(
                name="Task ID", value=task["id"], inline=True)
            embed.add_field(
                name="Task title", value=task["title"], inline=True)
            if project != {}:
                embed.add_field(
                    name="List name", value=project["name"], inline=True)
            embed.add_field(
                name="Task reminders", value=f"{len(task['reminders'])} reminders", inline=True)
            embed.add_field(
                name="Task subtasks", value=f"{len(task['items'])} reminders", inline=False)

            return {"embeds": [embed]}

    def complete_embed(self, name: str):
        task = self.ticktick.completeTask(name)

        if task is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Complete Task",
                color=0xffb301,
                description="No task found"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Complete Task",
                color=0xffb301,
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            # project = self.ticktick.getProjectById(task["projectId"])

            embed.add_field(
                name="Task ID", value=task["id"], inline=True)
            embed.add_field(
                name="Task title", value=task["title"], inline=True)
            # embed.add_field(
            #     name="List name", value=project["name"], inline=True)
            embed.add_field(
                name="Task reminders", value=f"{len(task['reminders'])} reminders", inline=True)
            embed.add_field(
                name="Task subtasks", value=f"{len(task['items'])} reminders", inline=False)

            return {"embeds": [embed]}

    def updatetask_embed(self, identifier: str, name: str = None, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        task = self.ticktick.getTask(identifier)

        if task is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Update Task",
                color=0xffb301,
                description="No task found"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            # Ignoring startDate and dueDate fields
            task["title"] = name if name is not None else task["title"]

            # print(project_id)
            # if project_id is not None:
            #     project = self.ticktick.getProject(project_id)
            #     print(project)
            #     if project is None or project == {}:
            #         pass
            #     else:
            #         task["projectId"] = project["id"]
            # print(task["projectId"])

            task["content"] = content if content is not None else task["content"]
            task["desc"] = desc if desc is not None else task["desc"]
            task["timeZone"] = time_zone if time_zone is not None else task["timeZone"]

            """
            To be implemented
            """
            # task["reminders"] = reminders if reminders is not None else task["reminders"]
            # task["repeat"] = repeat if repeat is not None else task["repeat"]
            # task["priority"] = priority if priority is not None else task["priority"]
            # task["sortOrder"] = sort_order if sort_order is not None else task["sortOrder"]
            # task["items"] = items if items is not None else task["items"]

            res = self.ticktick.updateTask(task)
            # print(res)

            return {"embeds": [embed]}

    def movetask_embed(self, task_details: str, list: str):
        task_details = self.ticktick.getTask(task_details)
        project_details = self.ticktick.getProject(list)

        # print(task_details)
        # print(project_details)
        # await interaction.response.send_message("STOP")
        # return
        if (task_details is None) or (project_details == {}):
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Move Task",
                color=0xffb301,
                description="Cannot move task"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            moved_task = self.ticktick.moveTask(
                task_details, project_details["id"])
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Move Task",
                color=discord.Colour.from_str(
                    project_details["color"] if project_details["color"] is not None else "#ffb301")
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            embed.add_field(
                name="Task ID", value=task_details["id"], inline=True)
            embed.add_field(
                name="Task title", value=task_details["title"], inline=True)
            # embed.add_field(
            #     name="List name", value=project["name"], inline=True)
            embed.add_field(
                name="Task reminders", value=f"{len(task_details['reminders'])} reminders", inline=True)
            embed.add_field(
                name="Task subtasks", value=f"{len(task_details['items'])} reminders", inline=False)

            return {"embeds": [embed]}

    def deletetask_embed(self, name: str):
        task = self.ticktick.deleteTask(name)
        # print(task)

        if task is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Delete Task",
                color=0xffb301,
                description="No task found"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Delete Task",
                color=0xffb301,
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            # project = self.ticktick.getProjectById(task["projectId"])

            embed.add_field(
                name="Task ID", value=task["id"], inline=True)
            embed.add_field(
                name="Task title", value=task["title"], inline=True)
            # embed.add_field(
            #     name="List name", value=project["name"], inline=True)
            embed.add_field(
                name="Task reminders", value=f"{len(task['reminders'])} reminders", inline=True)
            embed.add_field(
                name="Task subtasks", value=f"{len(task['items'])} reminders", inline=False)

            return {"embeds": [embed]}


    def getlist_embed(self, identifier: str):
        project = self.ticktick.getProject(identifier)

        if project == {}:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick list search",
                color=0xffb301,
                description="No lists found"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick list search",
                color=0xffb301,
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            tasks = self.ticktick.tasksFromProject(project["name"])
            for item in tasks:
                embed.add_field(
                    name="List ID", value=item["id"], inline=True)
                embed.add_field(
                    name="List title", value=item["title"], inline=True)
                embed.add_field(
                    name="List reminders", value=f"{len(item['reminders'])} reminders", inline=True)
                embed.add_field(
                    name="List subtasks", value=f"{len(item['items'])} reminders", inline=False)

            return {"embeds": [embed]}

    #
    # Projects
    #

    def listinfo_embed(self, identifier: str):
        project = self.ticktick.getProject(identifier)

        if project == {}:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick list search",
                color=0xffb301,
                description="List not found"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick list search",
                color=discord.Colour.from_str(project["color"])
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            embed.add_field(
                name="List ID", value=project["id"], inline=False)
            embed.add_field(
                name="List name", value=project["name"], inline=False)
            embed.add_field(
                name="List view mode", value=project["viewMode"], inline=False)

            return {"embeds": [embed]}

    """
    Function crashes(raises error) when you try to add a project if there's also maximum limit reachhed
    """

    def newlist_embed(self, name: str, color: str = None, project_type: str = 'TASK', folder_id: str = None):
        project = self.ticktick.createProject(
            name=name, color=color, project_type=project_type, folder_id=folder_id
        )

        # print(project)
        # await interaction.response.send_message("NI NI")
        # return
        if project is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick New Project",
                color=0xffb301,
                description="Project already exists"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            # await interaction.response.send_message("Dela")
            # return
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick New Project",
                color=discord.Colour.from_str(
                    project["color"] if project["color"] is not None else "#ffb301")
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            embed.add_field(
                name="List ID", value=project["id"], inline=False)
            embed.add_field(
                name="List name", value=project["name"], inline=False)
            embed.add_field(
                name="List view mode", value=project["viewMode"], inline=False)
            embed.add_field(
                name="List kind", value=project["kind"], inline=False)

            return {"embeds": [embed]}

    def changelist_embed(self, identifier: str, name: str = None, color: str = None, project_type: str = None, folder_id: str = None):
        updatedProject = self.ticktick.updateProject(
            identifier=identifier, name=name, color=color, project_type=project_type, folder_id=folder_id
        )

        if updatedProject is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Change List",
                color=0xffb301,
                description="List not found or changed"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            # print(updatedProject)
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Change List",
                color=discord.Colour.from_str(
                    updatedProject["color"] if updatedProject["color"] is not None else "#ffb301")
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            embed.add_field(
                name="List ID", value=updatedProject["id"], inline=False)
            embed.add_field(
                name="List name", value=updatedProject["name"], inline=False)
            embed.add_field(
                name="List color", value=updatedProject["color"], inline=False)
            # embed.add_field(
            #     name="List type", value=updatedProject["project_type"] if updatedProject["project_type"] is not None else "<no list type>", inline=False)
            # embed.add_field(
            #     name="List folder id", value=updatedProject["folder_id"] if updatedProject["folder_id"] is not None else "<no folder id>", inline=False)

            return {"embeds": [embed]}

    def deletelist_embed(self, identifier: str):
        project = self.ticktick.deleteProject(identifier)

        if project is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Delete Project",
                color=0xffb301,
                description="Project does not exist"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Delete Project",
                # color=discord.Colour.from_str(
                # project["color"] if project["color"] is not None else "#ffb301")
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            embed.add_field(
                name="List ID", value=project["id"], inline=False)
            embed.add_field(
                name="List name", value=project["name"], inline=False)
            embed.add_field(
                name="List view mode", value=project["viewMode"], inline=False)
            embed.add_field(
                name="List kind", value=project["kind"], inline=False)

            return {"embeds": [embed]}

    #
    # Tags
    #

    #
    # Aliases
    #

    def createalias_embed(self, command: str,  alias: str, arguments: str = "", cog_param: object = {}) -> dict:
        alias_fn = self.getFunctionByName(name=command)

        if alias_fn is None:
            embed = discord.Embed(
                title=":stopwatch: TickTick New Shortcut",
                color=discord.Colour.from_str("#ffb301"),
                description="Slash command not found"
            )
            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            return {"embeds": [embed]}
        else:
            insert_args = self.ticktick.parseShortcutArguments(arguments)
            cog_param.update(insert_args)

            inserted_data = self.ticktick.saveShortcut2(
                command=command, alias=alias, param=cog_param)

            embed = discord.Embed(
                title=":stopwatch: TickTick New Shortcut",
                color=discord.Colour.from_str("#ffb301"),
            )
            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
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

    def usealias_embed(self, alias: str):
        alias_data = self.ticktick.findSavedShortcut(alias=alias)

        fn_embed = self.getFunctionByName(alias_data["command"])

        embed = fn_embed(**alias_data["param"])

        return embed
