import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.BugReportFunctions import BugReportFunctions
from embeds.BugReportEmbeds import BugReportEmbeds
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


class BugReportCog(commands.Cog):
    bug_group = app_commands.Group(name="bug", description="Bug reports")

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("BugReportCog cog loaded")

    @bug_group.command(
        name="report",
        description="Report a bug or something that isn't working right",
    )
    @app_commands.describe(
        bug="Describe what went wrong",
        link="Optional link with more context (screenshots, message link, etc.)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def bugreport(
        self,
        interaction: discord.Interaction,
        bug: str,
        link: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        if not bug.strip():
            raise ValidationError("Bug report cannot be empty.", ephemeral=ephemeral)

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            document = await asyncio.to_thread(
                BugReportFunctions.insert_bug_report,
                interaction.guild_id,
                interaction.user.id,
                interaction.channel_id,
                bug,
                link,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while saving that bug report.",
                ephemeral=ephemeral,
                cause=exc,
            )

        payload = BugReportEmbeds.received_embed(document)
        await interaction.followup.send(ephemeral=ephemeral, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(BugReportCog(client))
