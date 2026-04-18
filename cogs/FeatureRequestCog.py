from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from services.visibility import (
    VISIBILITY_CHOICES,
    VISIBILITY_DESC,
    resolve_visibility_for_context,
)
from views.FeatureRequestModal import FeatureRequestModal


class FeatureRequestCog(commands.Cog):
    feature_group = app_commands.Group(
        name="feature", description="Feature requests"
    )

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("FeatureRequestCog cog loaded")

    @feature_group.command(
        name="request",
        description="Send a feature request to the bot author",
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def featurerequest(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility_for_context(
            interaction.guild_id,
            visibility,
            guild_default="private",
        )
        modal = FeatureRequestModal(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            ephemeral=ephemeral,
        )
        await interaction.response.send_modal(modal)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(FeatureRequestCog(client))


