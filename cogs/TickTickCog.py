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
from embeds.TickTickEmbeds import TickTickEmbeds
from dotenv import dotenv_values
env = dotenv_values(".env")


class TickTickCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.ticktick = TickTickFunctions(
            env["TICK_EMAIL"], env["TICK_PASSWORD"], env["TICK_ID"], env["TICK_SECRET"], env["TICK_URI"])
        self.embeds = TickTickEmbeds()

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

    @app_commands.command(name="newtask", description="TickTick add new task")
    @app_commands.describe(
        name="Name of the added task",
        project_id="Project of the task",
        content="Content of the task",
        desc="Description of the task",
        start_date="Start of the task",
        due_date="Due date of the task",
        time_zone="Task time zone",
        reminders="List of reminders",
        repeat="Does task repeat",
        priority="Priority of the task",
        sort_order="Order by which the task will be sorted",
        items="Subtasks of the task",
    )
    @app_commands.rename(
        desc="description",
        items="subtasks",
    )
    async def newtask(self, interaction: discord.Interaction, name: str, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        param = self.embeds.newtask_embed(name=name, project_id=project_id, content=content, desc=desc, start_date=start_date, due_date=due_date,
                                          time_zone=time_zone, reminders=reminders, repeat=repeat, priority=priority, sort_order=sort_order, items=items)

        await interaction.response.send_message(**param)

    @app_commands.command(name="newsubtask", description="TickTick add new subtask")
    @app_commands.describe(
        name="Name of the added task",
        parent="Parent task",
        project_id="Project of the task",
        content="Content of the task",
        desc="Description of the task",
        start_date="Start of the task",
        due_date="Due date of the task",
        time_zone="Task time zone",
        reminders="List of reminders",
        repeat="Does task repeat",
        priority="Priority of the task",
        sort_order="Order by which the task will be sorted",
        items="Subtasks of the task",
    )
    @app_commands.rename(
        desc="description",
        items="subtasks",
    )
    async def newsubtask(self, interaction: discord.Interaction, name: str, parent: str, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        param = self.embeds.newsubtask_embed(name=name, parent=parent, project_id=project_id, content=content, desc=desc, start_date=start_date,
                                             due_date=due_date, time_zone=time_zone, reminders=reminders, repeat=repeat, priority=priority, sort_order=sort_order, items=items)

        await interaction.response.send_message(**param)

    @app_commands.command(name="complete", description="TickTick complete a task")
    @app_commands.describe(
        name="Task to be completed"
    )
    async def complete(self, interaction: discord.Interaction, name: str):
        param = self.embeds.complete_embed(name=name)

        await interaction.response.send_message(**param)

    @app_commands.command(name="updatetask", description="TickTick update a task")
    @app_commands.describe(
        identifier="Task to be updated",
        name="Name of the added task",
        project_id="Project of the task",
        content="Content of the task",
        desc="Description of the task",
        start_date="Start of the task",
        due_date="Due date of the task",
        time_zone="Task time zone",
        reminders="List of reminders",
        repeat="Does task repeat",
        priority="Priority of the task",
        sort_order="Order by which the task will be sorted",
        items="Subtasks of the task",
    )
    @app_commands.rename(
        desc="description",
        items="subtasks",
    )
    async def updatetask(self, interaction: discord.Interaction, identifier: str, name: str = None, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        param = self.embeds.updatetask_embed(identifier=identifier, name=name, project_id=project_id, content=content, desc=desc, start_date=start_date,
                                             due_date=due_date, time_zone=time_zone, reminders=reminders, repeat=repeat, priority=priority, sort_order=sort_order, items=items)

        await interaction.response.send_message(**param)

    @app_commands.command(name="movetask", description="TickTick move a task to other list")
    @app_commands.describe(
        task_details="Task to be moved",
        list="Destination list of the moved task",
    )
    @app_commands.rename(
        task_details="name"
    )
    async def movetask(self, interaction: discord.Interaction, task_details: str, list: str):
        param = self.embeds.movetask_embed(
            task_details=task_details, list=list)

        await interaction.response.send_message(**param)

    @app_commands.command(name="deletetask", description="TickTick delete task")
    @app_commands.describe(
        name="Task to be deleted"
    )
    async def deletetask(self, interaction: discord.Interaction, name: str):
        param = self.embeds.deletetask_embed(name=name)

        await interaction.response.send_message(**param)

    @app_commands.command(name="getlist", description="TickTick get list")
    @app_commands.describe(
        identifier="List to be retrieved"
    )
    @app_commands.rename(
        identifier="name"
    )
    async def getlist(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.getlist_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    #
    # Projects
    #

    # @app_commands.command(name="newlist", description="TickTick create new list")
    # async def newlist(self, interaction: discord.Interaction):

    @app_commands.command(name="listinfo", description="TickTick get list info")
    @app_commands.describe(
        identifier="List info to be displayed",
    )
    @app_commands.rename(
        identifier="name"
    )
    async def listinfo(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.listinfo_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    @app_commands.command(name="newlist", description="TickTick create new list")
    @app_commands.describe(
        name="Name of the list",
        color="Color of the list",
        project_type="Type of the list",
        folder_id="Folder to which the list will be added",
    )
    async def newlist(self, interaction: discord.Interaction, name: str, color: str = None, project_type: str = 'TASK', folder_id: str = None):
        param = self.embeds.newlist_embed(
            name=name, color=color, project_type=project_type, folder_id=folder_id)

        await interaction.response.send_message(**param)

    @app_commands.command(name="changelist", description="TickTick change list")
    @app_commands.describe(
        name="Name of the list",
        color="Color of the list",
        project_type="Type of the list",
        folder_id="Folder to which the list will be added",
    )
    async def changelist(self, interaction: discord.Interaction, identifier: str, name: str = None, color: str = None, project_type: str = None, folder_id: str = None):
        param = self.embeds.changelist_embed(
            identifier=identifier, name=name, color=color, project_type=project_type, folder_id=folder_id)

        await interaction.response.send_message(**param)

    @app_commands.command(name="deletelist", description="TickTick delete list")
    @app_commands.describe(
        identifier="List to be deleted",
    )
    @app_commands.rename(
        identifier="name"
    )
    async def deletelist(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.deletelist_embed(identifier=identifier)

        await interaction.response.send_message(**param)


async def setup(client):
    await client.add_cog(TickTickCog(client), guilds=[discord.Object(id=864242668066177044)])
