# Color palette
# https://colorswall.com/palette/72717/
from typing import Optional

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
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


class AliasCog(commands.Cog):
    alias_group = app_commands.Group(name="alias", description="Alias shortcuts")

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

    @alias_group.command(name="use", description="Use an alias")
    @app_commands.describe(
        alias="Alias of a command to be used",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def usealias(
        self,
        interaction: discord.Interaction,
        alias: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        param = AliasEmbeds.usealias_embed(
            alias=alias,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(ephemeral=ephemeral, **param)

    @alias_group.command(name="find", description="Find aliases")
    @app_commands.describe(
        alias="Alias of a command to be used",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def findalias(
        self,
        interaction: discord.Interaction,
        alias: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
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

        await interaction.response.send_message(ephemeral=ephemeral, **param)

    @alias_group.command(name="popular", description="Most popular aliases")
    @app_commands.describe(
        n="Number of most popular aliases to be displayed",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def popularalias(
        self,
        interaction: discord.Interaction,
        n: int = 5,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        param = AliasEmbeds.popularalias_embed(
            n=n,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(ephemeral=ephemeral, **param)


async def setup(client):
    await client.add_cog(AliasCog(client))
