from re import A
from typing import Dict, Optional
import discord
from discord.ext import commands
from discord import app_commands
import inspect

from classes.TickTickFunctions import TickTickFunctions
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

