import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.FeatureRequestFunctions import FeatureRequestFunctions
from embeds.FeatureRequestEmbeds import FeatureRequestEmbeds
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


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
    @app_commands.describe(
        request="Describe the feature you'd like and why it would help",
        link="Optional link with more context (docs, screenshots, etc.)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def featurerequest(
        self,
        interaction: discord.Interaction,
        request: str,
        link: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        if not request.strip():
            await interaction.response.send_message(
                ephemeral=ephemeral,
                content="Feature request cannot be empty.",
            )
            return

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            document = await asyncio.to_thread(
                FeatureRequestFunctions.insert_feature_request,
                interaction.guild_id,
                interaction.user.id,
                interaction.channel_id,
                request,
                link,
            )
        except ValueError as exc:
            await interaction.followup.send(ephemeral=ephemeral, content=str(exc))
            return
        except Exception:
            await interaction.followup.send(
                ephemeral=ephemeral,
                content="Something went wrong while saving that feature request.",
            )
            return

        payload = FeatureRequestEmbeds.received_embed(document)
        await interaction.followup.send(ephemeral=ephemeral, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(FeatureRequestCog(client))
