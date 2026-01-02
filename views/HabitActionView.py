import asyncio

import discord

from classes.HabitFunctions import HabitFunctions


class HabitActionView(discord.ui.View):
    def __init__(
        self,
        habit_id: str,
        habit_name: str,
        user_id: int,
        *,
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.habit_id = habit_id
        self.habit_name = habit_name
        self.user_id = user_id

    async def _record(self, interaction: discord.Interaction, mode: str) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                ephemeral=True,
                content="Only the habit owner can update this habit.",
            )
            return

        await interaction.response.defer(ephemeral=True)
        updated = await asyncio.to_thread(
            HabitFunctions.add_completion,
            self.habit_id,
            interaction.guild_id,
            mode,
        )

        if not updated:
            await interaction.followup.send(
                ephemeral=True,
                content=f"Couldn't update '{self.habit_name}'.",
            )
            return

        await interaction.followup.send(
            ephemeral=True,
            content=f"Marked '{self.habit_name}' as {mode}.",
        )

    @discord.ui.button(label="complete", style=discord.ButtonStyle.success)
    async def complete_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._record(interaction, "complete")

    @discord.ui.button(label="skip", style=discord.ButtonStyle.secondary)
    async def skip_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._record(interaction, "skip")

    @discord.ui.button(label="incomplete", style=discord.ButtonStyle.danger)
    async def incomplete_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._record(interaction, "incomplete")
