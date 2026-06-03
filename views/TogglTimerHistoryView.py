import asyncio
from typing import Any, Optional

import discord

from classes.TogglFunctions import TogglFunctions
from classes.UserSettingsFunctions import UserSettingsFunctions


class TogglTimerHistoryView(discord.ui.View):
    def __init__(
        self,
        guild_id: Optional[int],
        user_id: int,
        timers: list[dict[str, Any]],
        page: int = 1,
        page_size: int = 5,
        sort: str = "descending",
        response_ephemeral: bool = True,
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.user_id = user_id
        self.all_timers = [dict(timer or {}) for timer in (timers or [])]
        self.page_size = max(1, min(int(page_size or 5), 5))
        self.sort = "ascending" if sort == "ascending" else "descending"
        self.page = max(1, int(page or 1))
        self.response_ephemeral = bool(response_ephemeral)
        self.total_pages = 1
        self._build()

    @classmethod
    async def from_dynamic_reference(
        cls,
        *,
        guild_id: Optional[int],
        user_id: int,
        page: int,
        sort: str,
        response_ephemeral: bool,
    ) -> Optional["TogglTimerHistoryView"]:
        api_key = await asyncio.to_thread(
            UserSettingsFunctions.get_toggl_api_key,
            user_id,
        )
        if not api_key:
            return None
        workspace_id = await asyncio.to_thread(
            UserSettingsFunctions.get_toggl_workspace_id,
            user_id,
        )
        toggl = TogglFunctions(api_key, workspace_id=workspace_id)
        timers = await asyncio.to_thread(toggl.getLastNTimeEntryHistory, 100)
        return cls(
            guild_id=guild_id,
            user_id=user_id,
            timers=timers or [],
            page=page,
            sort=sort,
            response_ephemeral=response_ephemeral,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            ephemeral=self.response_ephemeral,
            content="Only the user who opened this Toggl timer list can manage it.",
        )
        return False

    def _sorted_timers(self) -> list[dict[str, Any]]:
        reverse = self.sort != "ascending"
        return sorted(
            self.all_timers,
            key=lambda timer: str(
                timer.get("start") or timer.get("at") or timer.get("stop") or ""
            ),
            reverse=reverse,
        )

    def _page_slice(self) -> list[dict[str, Any]]:
        sorted_timers = self._sorted_timers()
        self.total_pages = max(1, (len(sorted_timers) + self.page_size - 1) // self.page_size)
        self.page = max(1, min(self.page, self.total_pages))
        start_index = (self.page - 1) * self.page_size
        return sorted_timers[start_index : start_index + self.page_size]

    def _build(self) -> None:
        from views.toggl_dynamic_items import TogglTimerHistoryButton

        self.clear_items()
        page_timers = self._page_slice()
        guild_id = int(self.guild_id or 0)

        for index in range(self.page_size):
            has_timer = index < len(page_timers)
            self.add_item(
                TogglTimerHistoryButton(
                    "info",
                    guild_id=guild_id,
                    user_id=self.user_id,
                    page=self.page,
                    sort=self.sort,
                    slot=index,
                    disabled=not has_timer,
                )
            )

        self.add_item(
            TogglTimerHistoryButton(
                "prev",
                guild_id=guild_id,
                user_id=self.user_id,
                page=self.page,
                sort=self.sort,
                disabled=self.page <= 1,
            )
        )
        self.add_item(
            TogglTimerHistoryButton(
                "next",
                guild_id=guild_id,
                user_id=self.user_id,
                page=self.page,
                sort=self.sort,
                disabled=self.page >= self.total_pages,
            )
        )
        self.add_item(
            TogglTimerHistoryButton(
                "sort",
                guild_id=guild_id,
                user_id=self.user_id,
                page=self.page,
                sort=self.sort,
            )
        )

    def _get_toggl(self) -> Optional[TogglFunctions]:
        api_key = UserSettingsFunctions.get_toggl_api_key(self.user_id)
        if not api_key:
            return None
        workspace_id = UserSettingsFunctions.get_toggl_workspace_id(self.user_id)
        return TogglFunctions(api_key, workspace_id=workspace_id)

    async def _send_error(
        self,
        interaction: discord.Interaction,
        message: str,
    ) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(
                ephemeral=self.response_ephemeral,
                content=message,
            )
            return
        await interaction.response.send_message(
            ephemeral=self.response_ephemeral,
            content=message,
        )

    async def _refresh_message(self, interaction: discord.Interaction) -> None:
        from embeds.TogglEmbeds import TogglEmbeds

        self._build()
        payload = await asyncio.to_thread(
            TogglEmbeds.timerhistory_payload_from_entries,
            self.all_timers,
            self.guild_id,
            self.user_id,
            page=self.page,
            page_size=self.page_size,
            sort=self.sort,
        )
        payload.pop("_toggl_timer_history_view", None)
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self, **payload)
            return
        await interaction.response.edit_message(view=self, **payload)

    async def _show_timer(
        self,
        interaction: discord.Interaction,
        timer_index: int,
    ) -> None:
        from embeds.TogglEmbeds import TogglEmbeds
        from views.TogglTimerView import TogglTimerView

        page_timers = self._page_slice()
        if timer_index >= len(page_timers):
            await interaction.response.defer(ephemeral=self.response_ephemeral)
            return

        timer_data = page_timers[timer_index]

        try:
            toggl = self._get_toggl()
        except Exception:
            await self._send_error(
                interaction,
                "I couldn't connect to Toggl for that timer action. Please try again.",
            )
            return
        if toggl is None:
            await self._send_error(interaction, "Your Toggl API key is missing.")
            return

        try:
            embed = await asyncio.to_thread(
                TogglEmbeds._single_timer_embed,
                title=":stopwatch: Toggl Timer",
                toggl=toggl,
                timer_data=timer_data,
            )
        except Exception:
            await self._send_error(
                interaction,
                "I couldn't load that Toggl timer right now. Please try again.",
            )
            return

        timer_view = TogglTimerView(
            guild_id=self.guild_id,
            user_id=self.user_id,
            timer_data=timer_data,
            is_active=False,
            response_ephemeral=self.response_ephemeral,
        )
        if interaction.response.is_done():
            await interaction.followup.send(
                embeds=[embed],
                view=timer_view,
                ephemeral=self.response_ephemeral,
            )
            return
        await interaction.response.send_message(
            embeds=[embed],
            view=timer_view,
            ephemeral=self.response_ephemeral,
        )
