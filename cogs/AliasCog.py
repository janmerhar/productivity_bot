# Color palette
# https://colorswall.com/palette/72717/
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
from config.env import env


class AliasCog(commands.Cog):
    def __init__(self, client):
        self.client = client

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
            if param.default is not None
            and type(param.default) != discord.utils._MissingSentinel
        }

    @app_commands.command(name="usealias", description="Shortcuts use alias")
    @app_commands.describe(
        alias="Alias of a command to be used",
    )
    async def usealias(self, interaction: discord.Interaction, alias: str):
        param = AliasEmbeds.usealias_embed(
            alias=alias,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="findaliases", description="Shortcuts find aliases")
    @app_commands.describe(
        alias="Alias of a command to be used",
    )
    async def findalias(self, interaction: discord.Interaction, alias: str):
        print(AliasCog.getFunctionByName(AliasCog, "usealias"))
        print(
            AliasCog.getDefaultParameters(
                AliasCog.getFunctionByName(AliasCog, "usealias")
            )
        )
        param = AliasEmbeds.findaliases_embed(
            alias=alias,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="popularalias", description="Most popular aliases")
    @app_commands.describe(n="Number of most popular aliases to be displayed")
    async def popularalias(self, interaction: discord.Interaction, n: int = 5):
        param = AliasEmbeds.popularalias_embed(
            n=n,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)


async def setup(client):
    await client.add_cog(AliasCog(client), guilds=[discord.Object(env["GUILD_ID"])])
