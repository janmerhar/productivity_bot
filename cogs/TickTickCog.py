# Color palette
# https://coolors.co/ffb301-ffffff-7892e3-607fde-ffb203
import discord
from discord.ext import commands
from discord import app_commands

from ticktick.oauth2 import OAuth2        # OAuth2 Manager
from ticktick.api import TickTickClient   # Main Interface
import datetime

import json
import os
import platform
import random
import sys
import aiohttp

from Classes.TickTickFunctions import TickTickFunctions
from dotenv import dotenv_values
env = dotenv_values(".env")


class TickTickCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.ticktick = TickTickFunctions(
            env["TICK_EMAIL"], env["TICK_PASSWORD"], env["TICK_ID"], env["TICK_SECRET"], env["TICK_URI"])

    # Events
    @commands.Cog.listener()
    async def on_ready(self):
        print("TickTickCog cog loaded")

    # Commands
    # @app_commands.command(name="", description="")
    # async def (self, interaction: discord.Interaction):

    #
    # Tasks
    #

    # ATM used for creating new tasks
    @app_commands.command(name="newtask", description="TickTick add new task")
    async def newtask(self, interaction: discord.Interaction, name: str, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
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

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="newsubtask", description="TickTick add new subtask")
    async def newsubtask(self, interaction: discord.Interaction):
        pass

    """
    Fix commented code
    """
    @app_commands.command(name="complete", description="TickTick complete a task")
    async def complete(self, interaction: discord.Interaction, name: str):
        task = self.ticktick.completeTask(name)
        # print(task)

        if task is None:
            embed = discord.Embed(
                title=":ballot_box_with_check: TickTick Complete Task",
                color=0xffb301,
                description="No task found"
            )

            embed.set_thumbnail(
                url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
            )

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="updatetask", description="TickTick update a task")
    async def updatetask(self, interaction: discord.Interaction):
        pass

    @app_commands.command(name="movetask", description="TickTick move a task to other list")
    async def movetask(self, interaction: discord.Interaction, task_details: str, list: str):
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

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)

    """
    Fix commented code
    """
    @app_commands.command(name="deletetask", description="TickTick delete task")
    async def deletetask(self, interaction: discord.Interaction, name: str):
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

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)

    """
    Implement:
    - Better printout for reminders
    - Better printout for subtasks
    """
    @app_commands.command(name="getlist", description="TickTick get list")
    async def getlist(self, interaction: discord.Interaction, identifier: str):
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

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)

    #
    # Projects
    #

    # @app_commands.command(name="newlist", description="TickTick create new list")
    # async def newlist(self, interaction: discord.Interaction):

    @app_commands.command(name="listinfo", description="TickTick get list info")
    async def listinfo(self, interaction: discord.Interaction, identifier: str):
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

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)

    """
    Function crashes(raises error) when you try to add a project if there's also maximum limit reachhed
    """
    @app_commands.command(name="newlist", description="TickTick create new list")
    async def newlist(self, interaction: discord.Interaction, name: str, color: str = None, project_type: str = 'TASK', folder_id: str = None):
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

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)

    @app_commands.command(name="changelist", description="TickTick change list")
    async def changelist(self, interaction: discord.Interaction, identifier: str, name: str = None, color: str = None, project_type: str = None, folder_id: str = None):
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

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)

    """
    Passing color does not work
    """
    @app_commands.command(name="deletelist", description="TickTick delete list")
    async def deletelist(self, interaction: discord.Interaction, identifier: str):
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

            await interaction.response.send_message(embed=embed)
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

            await interaction.response.send_message(embed=embed)


async def setup(client):
    await client.add_cog(TickTickCog(client), guilds=[discord.Object(id=864242668066177044)])
