from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.SlashCommandRouter import SlashCommandRouter
from config.env import settings
from services.visibility import (
    VISIBILITY_CHOICES,
    VISIBILITY_DESC,
    resolve_visibility_for_context,
)


class RouterCog(commands.Cog):
    assistant_group = app_commands.Group(
        name="assistant", description="Assistant utilities"
    )

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("RouterCog cog loaded")

    @assistant_group.command(
        name="run",
        description="Run an existing slash command from natural language",
    )
    @app_commands.describe(
        query="Instruction for the bot",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def run(
        self,
        interaction: discord.Interaction,
        query: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility_for_context(
            interaction.guild_id,
            visibility,
            guild_default="private",
        )
        if settings.dev_mode:
            await interaction.response.send_message(
                "This command is in development.",
                ephemeral=ephemeral,
            )
            return
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        router = SlashCommandRouter(
            interaction.client.tree,
            excluded={"run"},
        )
        await router.dispatch(interaction, query, ephemeral_default=ephemeral)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(RouterCog(client))
