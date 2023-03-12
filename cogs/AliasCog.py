# Color palette
# https://colorswall.com/palette/72717/
from dotenv import dotenv_values
import discord
from discord.ext import commands
from discord import app_commands

import json
import os
import platform
import random
import sys
import aiohttp

from embeds.AliasEmbeds import AliasEmbeds
from embeds.TogglEmbeds import TogglEmbeds
env = dotenv_values(".env")


class AliasCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.embeds = AliasEmbeds()

        self.embeds_classes = {"toggl": TogglEmbeds}

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("Alias cog loaded")



async def setup(client):
    await client.add_cog(AliasCog(client), guilds=[discord.Object(id=864242668066177044)])
