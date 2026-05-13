import asyncio
from typing import Optional

import discord
from discord.utils import MISSING

from classes.HabitFunctions import HabitFunctions
from embeds.HabitEmbeds import HabitEmbeds


class HabitActionView(discord.ui.View):
    def __init__(
        self,
        habit_id: str,
        habit_name: str,
        user_id: int,
        *,
        today_status: Optional[str] = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.habit_id = habit_id
        self.habit_name = habit_name
        self.user_id = user_id
        self.today_status = today_status
        self.message: Optional[discord.Message] = None
        self._rebuild_items(today_status=self.today_status)

    def button_view_kind(self) -> str:
        return "basic"

    def _rebuild_items(
        self,
        *,
        disabled: bool = False,
        today_status: Optional[str] = None,
    ) -> None:
        from views.habit_dynamic_items import (
            HabitCompleteButton,
            HabitSkipButton,
        )

        normalized_status = str(today_status or "").strip().lower() or None
        complete_disabled = disabled or normalized_status == "complete"
        skip_disabled = disabled or normalized_status == "skip"

        self.clear_items()
        self.add_item(
            HabitCompleteButton(
                self.habit_id,
                self.user_id,
                view_kind=self.button_view_kind(),
                disabled=complete_disabled,
            )
        )
        self.add_item(
            HabitSkipButton(
                self.habit_id,
                self.user_id,
                view_kind=self.button_view_kind(),
                disabled=skip_disabled,
            )
        )

    async def refresh_message(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message] = None,
        habit: Optional[dict] = None,
        content=MISSING,
    ) -> bool:
        if habit is None:
            habit = await asyncio.to_thread(
                HabitFunctions.fetch_habit,
                self.habit_id,
                interaction.guild_id,
                self.user_id,
            )

        if habit is None:
            self.today_status = None
            self._rebuild_items(disabled=True)
            embed = discord.Embed(
                title=self.habit_name or "Habit",
                description="This habit is no longer available.",
                color=discord.Colour.red(),
            )
        else:
            self.habit_name = str(habit.get("name") or self.habit_name or "Habit")
            self.today_status = HabitFunctions.today_status(habit)
            self._rebuild_items(today_status=self.today_status)
            payload = HabitEmbeds.habit_item_embed(
                habit,
                self.today_status,
                HabitFunctions.recent_progress(habit, days=5),
            )
            embed = payload["embed"]

        if getattr(interaction, "message", None) is not None:
            try:
                await interaction.edit_original_response(
                    content=content,
                    embed=embed,
                    view=self,
                )
                self.message = interaction.message
                return True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        candidates = []
        for candidate in (source_message, interaction.message, self.message):
            if candidate is None:
                continue
            if any(
                getattr(existing, "id", None) == getattr(candidate, "id", None)
                for existing in candidates
            ):
                continue
            candidates.append(candidate)

        for candidate in candidates:
            try:
                await candidate.edit(content=content, embed=embed, view=self)
                self.message = candidate
                return True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        source_message_id = getattr(source_message, "id", None)
        if source_message_id is not None:
            try:
                await interaction.followup.edit_message(
                    source_message_id,
                    content=content,
                    embed=embed,
                    view=self,
                )
                self.message = source_message
                return True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        return False
