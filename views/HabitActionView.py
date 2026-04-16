import asyncio

import discord

from classes.HabitFunctions import HabitFunctions
from embeds.HabitEmbeds import HabitEmbeds


class HabitActionView(discord.ui.View):
    def __init__(
        self,
        habit_id: str,
        habit_name: str,
        user_id: int,
        *,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.habit_id = habit_id
        self.habit_name = habit_name
        self.user_id = user_id
        self._rebuild_items()

    def _rebuild_items(self, *, disabled: bool = False) -> None:
        from views.habit_dynamic_items import (
            HabitCompleteButton,
            HabitIncompleteButton,
            HabitSkipButton,
        )

        self.clear_items()
        self.add_item(
            HabitCompleteButton(
                self.habit_id,
                self.user_id,
                disabled=disabled,
            )
        )
        self.add_item(
            HabitSkipButton(
                self.habit_id,
                self.user_id,
                disabled=disabled,
            )
        )
        self.add_item(
            HabitIncompleteButton(
                self.habit_id,
                self.user_id,
                disabled=disabled,
            )
        )

    async def refresh_message(self, interaction: discord.Interaction) -> bool:
        habit = await asyncio.to_thread(
            HabitFunctions.fetch_habit,
            self.habit_id,
            interaction.guild_id,
        )

        if habit is None:
            self._rebuild_items(disabled=True)
            embed = discord.Embed(
                title=self.habit_name or "Habit",
                description="This habit is no longer available.",
                color=discord.Colour.red(),
            )
        else:
            self.habit_name = str(habit.get("name") or self.habit_name or "Habit")
            self._rebuild_items()
            payload = HabitEmbeds.habit_item_embed(
                habit,
                HabitFunctions.today_status(habit),
                HabitFunctions.recent_progress(habit, days=5),
            )
            embed = payload["embed"]

        if interaction.message is None:
            return False

        try:
            await interaction.message.edit(embed=embed, view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False
        return True
