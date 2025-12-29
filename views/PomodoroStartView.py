from typing import Optional

import discord


class PomodoroStartView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        join_url: Optional[str] = None,
        *,
        timeout: float = 21600,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        if join_url:
            self.add_item(discord.ui.Button(label="Join Voice", url=join_url))

    @discord.ui.button(label="Stop Pomodoro", style=discord.ButtonStyle.danger)
    async def stop_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=True,
                content="Only the user who started this pomodoro can stop it.",
            )
            return

        await interaction.response.defer(ephemeral=True)
        from classes.PomodoroFunctions import PomodoroFunctions

        result = await PomodoroFunctions.stop_user_pomodoro(interaction)
        await interaction.followup.send(ephemeral=True, content=result.message)
