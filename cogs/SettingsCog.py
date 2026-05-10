import asyncio

import discord
from discord import app_commands
from discord.ext import commands

from classes.UserSettingsFunctions import UserSettingsFunctions
from embeds.SettingsEmbeds import SettingsEmbeds
from views.TimezoneModal import TimezoneModal
from views.TogglApiKeyModal import TogglApiKeyModal


async def _noop(interaction: discord.Interaction, value: str) -> None:
    pass


class SettingsCog(commands.Cog):
    settings_group = app_commands.Group(
        name="settings", description="Manage your personal bot settings"
    )
    set_group = app_commands.Group(
        name="set", description="Update a setting"
    )
    settings_group.add_command(set_group)

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("SettingsCog cog loaded")

    @app_commands.command(name="info", description="Show what this bot does and how to start")
    async def info(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            embed=SettingsEmbeds.info_embed(), ephemeral=True
        )

    @set_group.command(
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

    @set_group.command(
        name="toggl",
        description="Set your Toggl API key",
    )
    async def set_toggl(self, interaction: discord.Interaction) -> None:
        modal = TogglApiKeyModal(
            user_id=interaction.user.id,
            on_api_key_resolved=_noop,
            continue_message="Toggl API key saved.",
            response_ephemeral=True,
        )
        await interaction.response.send_modal(modal)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(SettingsCog(client))
