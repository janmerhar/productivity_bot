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


    def getFunctionByName(obj, name):
        try:
            fn = getattr(obj, f"{name}")
            return fn
        except:
            return None

    def getDefaultParameters(cog_fn):
        return {
            param.name: param.default
            for param in cog_fn.parameters
            if param.default is not None and type(param.default) != discord.utils._MissingSentinel
        }

    @app_commands.command(name="usealias", description="Shortcuts use alias")
    @app_commands.describe(
        alias="Alias of a command to be used",
    )
    async def usealias(self, interaction: discord.Interaction, alias: str):
        param = self.embeds.usealias_embed(alias=alias)

        await interaction.response.send_message(**param)


async def setup(client):
    await client.add_cog(AliasCog(client), guilds=[discord.Object(id=864242668066177044)])
