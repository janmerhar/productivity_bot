import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.UserSettingsFunctions import UserSettingsFunctions
from views.TimezoneModal import TimezoneModal
from views.TogglApiKeyModal import TogglApiKeyModal


async def _noop(interaction: discord.Interaction, value: str) -> None:
    pass


class SettingsCog(commands.Cog):
    settings_group = app_commands.Group(
        name="settings", description="Manage your personal bot settings"
    )

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("SettingsCog cog loaded")

    @settings_group.command(
        name="timezone",
        description="Set your timezone for scheduling and reminders",
    )
    async def set_timezone(self, interaction: discord.Interaction) -> None:
        current_timezone = await asyncio.to_thread(
            UserSettingsFunctions.get_timezone,
            interaction.user.id,
        )
        modal = TimezoneModal(
            user_id=interaction.user.id,
            on_timezone_resolved=_noop,
            continue_message="Timezone set to `{timezone}`.",
            response_ephemeral=True,
            default_timezone=current_timezone,
        )
        await interaction.response.send_modal(modal)

    @settings_group.command(
        name="toggl-key",
        description="Set your Toggl API key",
    )
    async def set_toggl_key(self, interaction: discord.Interaction) -> None:
        modal = TogglApiKeyModal(
            user_id=interaction.user.id,
            on_api_key_resolved=_noop,
            continue_message="Toggl API key saved.",
            response_ephemeral=True,
        )
        await interaction.response.send_modal(modal)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(SettingsCog(client))
