from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from services.visibility import (
    VISIBILITY_CHOICES,
    VISIBILITY_DESC,
    resolve_visibility_for_context,
)
from views.BugReportModal import BugReportModal


class BugReportCog(commands.Cog):
    bug_group = app_commands.Group(name="bug", description="Report bugs")

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("BugReportCog cog loaded")

    @bug_group.command(
        name="report",
        description="Report a bug",
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def bugreport(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility_for_context(
            interaction.guild_id,
            visibility,
            guild_default="private",
        )
        modal = BugReportModal(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            channel_id=interaction.channel_id,
            ephemeral=ephemeral,
        )
        await interaction.response.send_modal(modal)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(BugReportCog(client))
