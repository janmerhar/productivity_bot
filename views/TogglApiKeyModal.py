import asyncio
from typing import Awaitable, Callable, Optional

import discord

from classes.TogglFunctions import TogglFunctions
from classes.UserSettingsFunctions import UserSettingsFunctions
from services.error_reporting import UserVisibleError, handle_interaction_error


class TogglApiKeyModal(discord.ui.Modal, title="Set Toggl API Key"):
    api_key = discord.ui.TextInput(
        label="Toggl API Key",
        placeholder="Paste your Toggl API token",
        required=True,
        max_length=200,
    )

    def __init__(
        self,
        user_id: int,
        on_api_key_resolved: Callable[[discord.Interaction, str], Awaitable[None]],
        continue_message: Optional[str] = None,
    ):
        super().__init__()
        self._user_id = int(user_id)
        self._on_api_key_resolved = on_api_key_resolved
        self._continue_message = continue_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "This form is only for the user who started the command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        cleaned = str(self.api_key.value or "").strip()
        if not cleaned:
            await interaction.followup.send(
                "API key cannot be empty.",
                ephemeral=True,
            )
            return

        workspace_id = None
        try:
            workspace_id = await asyncio.to_thread(self._resolve_workspace_id, cleaned)
        except Exception:
            workspace_id = None

        try:
            await asyncio.to_thread(
                UserSettingsFunctions.set_toggl_api_key,
                self._user_id,
                cleaned,
                workspace_id,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "I couldn't save that Toggl API key right now. Please try again.",
                    ephemeral=True,
                    cause=exc,
                ),
                ephemeral=True,
            )
            return

        try:
            if self._continue_message:
                await interaction.followup.send(
                    content=self._continue_message,
                    ephemeral=True,
                )
            await self._on_api_key_resolved(interaction, cleaned)
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "API key was saved, but I couldn't continue that action.",
                    ephemeral=True,
                    cause=exc,
                ),
                ephemeral=True,
            )

    @staticmethod
    def _resolve_workspace_id(api_key: str) -> int:
        toggl = TogglFunctions(api_key)
        workspace_id = toggl.workspace_id
        if workspace_id is None:
            raise ValueError("Could not determine Toggl workspace.")
        return int(workspace_id)
