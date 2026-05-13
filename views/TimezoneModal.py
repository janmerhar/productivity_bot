import asyncio
from typing import Awaitable, Callable, Optional

import discord

from classes.UserSettingsFunctions import UserSettingsFunctions
from services.error_reporting import UserVisibleError, handle_interaction_error


class TimezoneModal(discord.ui.Modal, title="Set Timezone"):
    timezone = discord.ui.TextInput(
        label="Timezone",
        placeholder="America/New_York, berlin, pst, utc+2",
        required=True,
        max_length=100,
    )

    def __init__(
        self,
        user_id: int,
        on_timezone_resolved: Callable[[discord.Interaction, str], Awaitable[None]],
        *,
        continue_message: Optional[str] = None,
        response_ephemeral: bool = True,
        default_timezone: Optional[str] = None,
    ):
        super().__init__()
        self._user_id = int(user_id)
        self._on_timezone_resolved = on_timezone_resolved
        self._continue_message = continue_message
        self._response_ephemeral = bool(response_ephemeral)
        if default_timezone:
            self.timezone.default = default_timezone[:100]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "This form is only for the user who started the command.",
                ephemeral=self._response_ephemeral,
            )
            return

        await interaction.response.defer(ephemeral=self._response_ephemeral)

        raw_timezone = str(self.timezone.value or "").strip()
        resolved_timezone = await asyncio.to_thread(
            UserSettingsFunctions.resolve_timezone_input,
            raw_timezone,
        )
        if not resolved_timezone:
            await interaction.followup.send(
                (
                    "I couldn't understand that timezone. "
                    "Try values like `America/New_York`, `berlin`, `pst`, or `utc+2`."
                ),
                ephemeral=self._response_ephemeral,
            )
            return

        try:
            await asyncio.to_thread(
                UserSettingsFunctions.set_timezone,
                self._user_id,
                resolved_timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "I couldn't save that timezone right now. Please try again.",
                    ephemeral=self._response_ephemeral,
                    cause=exc,
                ),
                ephemeral=self._response_ephemeral,
            )
            return

        try:
            if self._continue_message:
                await interaction.followup.send(
                    content=self._continue_message.format(timezone=resolved_timezone),
                    ephemeral=self._response_ephemeral,
                )
            await self._on_timezone_resolved(interaction, resolved_timezone)
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Timezone was saved, but I couldn't continue that action.",
                    ephemeral=self._response_ephemeral,
                    cause=exc,
                ),
                ephemeral=self._response_ephemeral,
            )
