import asyncio
import math
from typing import Dict, List, Optional

import discord

from classes.HabitFunctions import HabitFunctions
from embeds.HabitEmbeds import HabitEmbeds
from services import habit_list_sessions
from views.HabitActionView import HabitActionView


class HabitListView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(
        self,
        *,
        habits: List[Dict],
        scope_label: str,
        scope_value: str,
        mode: str,
        guild_id: Optional[int],
        channel_id: Optional[int],
        user_id: Optional[int],
        response_ephemeral: bool = False,
        page: int = 1,
        session_id: Optional[str] = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self._all_habits = list(habits)
        self.habits = list(habits)
        self.scope_label = str(scope_label or "").strip()
        self.scope_value = (
            "personal" if str(scope_value or "").strip() == "personal" else "channel"
        )
        self.mode = "incomplete" if str(mode or "").strip() == "incomplete" else "all"
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.response_ephemeral = bool(response_ephemeral)
        self.page_size = self.PAGE_SIZE
        self.total_pages = max(1, math.ceil(len(self.habits) / self.page_size))
        self.page = max(1, min(int(page or 1), self.total_pages))
        self.session_id = str(session_id or "").strip() or None
        self.message: Optional[discord.Message] = None
        if self.session_id is not None:
            self._build()

    @classmethod
    async def from_session(
        cls,
        interaction: discord.Interaction,
        session_id: str,
    ) -> Optional["HabitListView"]:
        session = await asyncio.to_thread(
            habit_list_sessions.get_session,
            session_id,
        )
        if session is None:
            return None

        habits = await asyncio.to_thread(
            HabitFunctions.list_habits,
            session.get("guild_id"),
            session.get("user_id"),
            session.get("channel_id"),
            str(session.get("mode") or "all"),
            str(session.get("scope_value") or "channel"),
        )
        view = cls(
            habits=habits,
            scope_label=str(session.get("scope_label") or "").strip(),
            scope_value=str(session.get("scope_value") or "channel").strip(),
            mode=str(session.get("mode") or "all").strip(),
            guild_id=session.get("guild_id"),
            channel_id=session.get("channel_id"),
            user_id=session.get("user_id"),
            response_ephemeral=bool(session.get("response_ephemeral", False)),
            page=max(1, int(session.get("page") or 1)),
            session_id=str(session.get("session_id") or session_id).strip(),
        )
        view.message = interaction.message
        await view.ensure_session()
        return view

    def session_state(self) -> dict:
        return {
            "scope_label": self.scope_label,
            "scope_value": self.scope_value,
            "mode": self.mode,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "page": self.page,
            "response_ephemeral": self.response_ephemeral,
        }

    async def ensure_session(self) -> str:
        if self.session_id is None:
            self.session_id = await asyncio.to_thread(
                habit_list_sessions.create_session,
                self.session_state(),
            )
        else:
            await self.save_session()
        self._build()
        return self.session_id

    async def save_session(self) -> None:
        if self.session_id is None:
            return
        await asyncio.to_thread(
            habit_list_sessions.save_session,
            self.session_id,
            self.session_state(),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id is None or interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "Only the user who opened this habit list can change pages.",
            ephemeral=self.response_ephemeral,
        )
        return False

    def _page_slice(self) -> List[Dict]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.habits[start:end]

    def _page_item(self, slot_index: int) -> Optional[Dict]:
        page_items = self._page_slice()
        if 0 <= slot_index < len(page_items):
            return page_items[slot_index]
        return None

    @staticmethod
    def _truncate(text: str, limit: int = 120) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3].rstrip()}..."

    def _mode_label(self) -> str:
        return "Incomplete" if self.mode == "incomplete" else "All"

    def _title(self) -> str:
        if self.scope_label:
            return f"Habits - {self.scope_label}"
        return "Habits"

    def _embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self._title(),
            color=discord.Colour.blurple(),
        )

        page_habits = self._page_slice()
        if not page_habits:
            if self.mode == "incomplete":
                embed.description = "No incomplete habits for today."
            else:
                embed.description = "No habits found."
            embed.set_footer(
                text=(
                    f"Page {self.page}/{self.total_pages} | "
                    f"Habits: {len(self.habits)} | Mode: {self._mode_label()}"
                )
            )
            return embed

        for display_index, habit in enumerate(page_habits, start=1):
            name = self._truncate(str(habit.get("name") or "Habit"), 100) or "Habit"
            description = self._truncate(str(habit.get("description") or ""), 180)
            status = HabitFunctions.today_status(habit)
            progress = HabitFunctions.recent_progress(habit, days=5)

            value_lines = []
            if description:
                value_lines.append(description)
            value_lines.append(
                f"Created: {HabitEmbeds._format_created(habit.get('created'))}"
            )
            value_lines.append(f"Today: {HabitEmbeds._format_status(status)}")
            if progress:
                value_lines.append(HabitEmbeds.progress_line(progress))

            embed.add_field(
                name=f"{display_index}. {name}",
                value="\n".join(value_lines),
                inline=False,
            )

        embed.set_footer(
            text=(
                f"Page {self.page}/{self.total_pages} | "
                f"Habits: {len(self.habits)} | Mode: {self._mode_label()}"
            )
        )
        return embed

    def payload(self) -> dict:
        return {"embed": self._embed()}

    async def _reload_habits(self) -> None:
        self._all_habits = await asyncio.to_thread(
            HabitFunctions.list_habits,
            self.guild_id,
            self.user_id,
            self.channel_id,
            self.mode,
            self.scope_value,
        )
        self.habits = list(self._all_habits)
        self.total_pages = max(1, math.ceil(len(self.habits) / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))

    async def _notify_missing_message(self, interaction: discord.Interaction) -> None:
        message = "That habit list is no longer available. Run `/habit list` again."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(ephemeral=True, content=message)
            else:
                await interaction.response.send_message(ephemeral=True, content=message)
        except Exception:
            return

    async def _safe_refresh_message(self, interaction: discord.Interaction) -> bool:
        self._build()
        await self.save_session()
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self, **self.payload())
            else:
                await interaction.response.edit_message(view=self, **self.payload())
            self.message = interaction.message
            return True
        except discord.NotFound:
            await self._notify_missing_message(interaction)
            return False

    async def open_habit_details(
        self,
        interaction: discord.Interaction,
        habit: Optional[Dict],
    ) -> None:
        habit_id = str((habit or {}).get("_id") or "").strip()
        if not habit_id:
            await interaction.response.defer(ephemeral=self.response_ephemeral)
            return

        current_habit = await asyncio.to_thread(
            HabitFunctions.fetch_habit,
            habit_id,
            self.guild_id,
            self.user_id,
        )
        if current_habit is None:
            await self._reload_habits()
            await self._safe_refresh_message(interaction)
            return

        habit_cog = interaction.client.get_cog("HabitCog")
        payload = HabitEmbeds.habit_item_embed(
            current_habit,
            HabitFunctions.today_status(current_habit),
            HabitFunctions.recent_progress(current_habit, days=5),
        )

        if habit_cog is not None and hasattr(habit_cog, "_build_created_habit_view"):
            payload["view"] = habit_cog._build_created_habit_view(
                current_habit,
                ephemeral=self.response_ephemeral,
            )
        else:
            payload["view"] = HabitActionView(
                habit_id,
                str(current_habit.get("name") or "Habit"),
                interaction.user.id,
            )

        await interaction.response.defer(ephemeral=self.response_ephemeral)
        posted_message = await interaction.followup.send(
            ephemeral=self.response_ephemeral,
            wait=True,
            **payload,
        )
        payload["view"].message = posted_message

    def _build(self) -> None:
        self.clear_items()
        if self.session_id is None:
            return

        from views.habit_list_dynamic_items import (
            HabitListNextButton,
            HabitListPrevButton,
            HabitListShowButton,
        )

        for slot_index in range(self.page_size):
            self.add_item(
                HabitListShowButton(
                    self.session_id,
                    slot_index,
                    disabled=self._page_item(slot_index) is None,
                )
            )

        self.add_item(
            HabitListPrevButton(
                self.session_id,
                disabled=self.page <= 1,
            )
        )
        self.add_item(
            HabitListNextButton(
                self.session_id,
                disabled=self.page >= self.total_pages,
            )
        )
