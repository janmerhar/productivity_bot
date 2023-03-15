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

from classes.TickTickFunctions import TickTickFunctions
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

    # ATM used for creating new tasks
    @app_commands.command(name="newtask", description="TickTick add new task")
    async def newtask(self, interaction: discord.Interaction, name: str, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        param = self.embeds.newtask_embed(name=name, project_id=project_id, content=content, desc=desc, start_date=start_date, due_date=due_date,
                                          time_zone=time_zone, reminders=reminders, repeat=repeat, priority=priority, sort_order=sort_order, items=items)

        await interaction.response.send_message(**param)

    @app_commands.command(name="newsubtask", description="TickTick add new subtask")
    async def newsubtask(self, interaction: discord.Interaction, name: str, parent: str, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        param = self.embeds.newsubtask_embed(name=name, parent=parent, project_id=project_id, content=content, desc=desc, start_date=start_date,
                                             due_date=due_date, time_zone=time_zone, reminders=reminders, repeat=repeat, priority=priority, sort_order=sort_order, items=items)

        await interaction.response.send_message(**param)

    @app_commands.command(name="complete", description="TickTick complete a task")
    async def complete(self, interaction: discord.Interaction, name: str):
        param = self.embeds.complete_embed(name=name)

        await interaction.response.send_message(**param)

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
    async def updatetask(self, interaction: discord.Interaction, identifier: str, name: str = None, project_id: str = None, content: str = None, desc: str = None, start_date: str = None, due_date: str = None, time_zone: str = None, reminders: str = None, repeat: str = None, priority: str = None, sort_order: str = None, items: str = None):
        param = self.embeds.updatetask_embed(identifier=identifier, name=name, project_id=project_id, content=content, desc=desc, start_date=start_date,
                                             due_date=due_date, time_zone=time_zone, reminders=reminders, repeat=repeat, priority=priority, sort_order=sort_order, items=items)

        await interaction.response.send_message(**param)

    @app_commands.command(name="movetask", description="TickTick move a task to other list")
    async def movetask(self, interaction: discord.Interaction, task_details: str, list: str):
        param = self.embeds.movetask_embed(
            task_details=task_details, list=list)

        await interaction.response.send_message(**param)

    @app_commands.command(name="deletetask", description="TickTick delete task")
    async def deletetask(self, interaction: discord.Interaction, name: str):
        param = self.embeds.deletetask_embed(name=name)

        await interaction.response.send_message(**param)

    @app_commands.command(name="getlist", description="TickTick get list")
    async def getlist(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.getlist_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    #
    # Projects
    #

    # @app_commands.command(name="newlist", description="TickTick create new list")
    # async def newlist(self, interaction: discord.Interaction):

    @app_commands.command(name="listinfo", description="TickTick get list info")
    async def listinfo(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.listinfo_embed(identifier=identifier)

        await interaction.response.send_message(**param)

    @app_commands.command(name="newlist", description="TickTick create new list")
    async def newlist(self, interaction: discord.Interaction, name: str, color: str = None, project_type: str = 'TASK', folder_id: str = None):
        param = self.embeds.newlist_embed(
            name=name, color=color, project_type=project_type, folder_id=folder_id)

        await interaction.response.send_message(**param)

    @app_commands.command(name="changelist", description="TickTick change list")
    async def changelist(self, interaction: discord.Interaction, identifier: str, name: str = None, color: str = None, project_type: str = None, folder_id: str = None):
        param = self.embeds.changelist_embed(
            identifier=identifier, name=name, color=color, project_type=project_type, folder_id=folder_id)

        await interaction.response.send_message(**param)

    @app_commands.command(name="deletelist", description="TickTick delete list")
    async def deletelist(self, interaction: discord.Interaction, identifier: str):
        param = self.embeds.deletelist_embed(identifier=identifier)

        await interaction.response.send_message(**param)


async def setup(client):
    await client.add_cog(TickTickCog(client), guilds=[discord.Object(id=864242668066177044)])
