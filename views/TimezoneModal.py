import asyncio

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

    def __init__(self, user_id: int):
        super().__init__()
        self._user_id = int(user_id)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "This form is only for the user who started the command.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

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
                ephemeral=True,
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
                    ephemeral=True,
                    cause=exc,
                ),
                ephemeral=True,
            )
            return

        cog = interaction.client.get_cog("TodoCog")
        if cog is None:
            await interaction.followup.send(
                "Todo service is not available right now. Please try again.",
                ephemeral=True,
            )
            return

        todo_cog = cog
        pending = todo_cog.pop_pending_timezone_add(self._user_id)
        if not pending:
            await interaction.followup.send(
                (
                    f"Saved timezone `{resolved_timezone}`. "
                    "Your pending `/todo add` request expired, so run it again."
                ),
                ephemeral=True,
            )
            return

        try:
            await todo_cog.resume_item_add_from_pending(
                interaction,
                pending,
                resolved_timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Timezone was saved, but I couldn't continue `/todo add`.",
                    ephemeral=True,
                    cause=exc,
                ),
                ephemeral=True,
            )
