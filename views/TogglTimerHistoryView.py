import asyncio
from typing import Any, Optional

import discord

from classes.TogglFunctions import TogglFunctions
from classes.UserSettingsFunctions import UserSettingsFunctions
from views.TogglTimeEntryEditModal import TogglTimeEntryEditModal


class TogglTimerHistoryView(discord.ui.View):
    def __init__(
        self,
        guild_id: Optional[int],
        user_id: int,
        timers: list[dict[str, Any]],
        limit: int = 5,
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.user_id = user_id
        self.limit = max(1, min(int(limit or 5), 5))
        self.timers = [dict(timer or {}) for timer in (timers or [])][: self.limit]
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            ephemeral=True,
            content="Only the user who opened this Toggl timer list can manage it.",
        )
        return False

    def _build(self) -> None:
        self.clear_items()

        for index in range(self.limit):
            item_number = index + 1
            has_timer = index < len(self.timers)

            start_button = discord.ui.Button(
                label=str(item_number),
                emoji="▶️",
                style=discord.ButtonStyle.success,
                row=0,
                disabled=not has_timer,
            )

            async def _start_callback(
                interaction: discord.Interaction,
                timer_index: int = index,
            ) -> None:
                await self._start_timer(interaction, timer_index)

            start_button.callback = _start_callback
            self.add_item(start_button)

            edit_button = discord.ui.Button(
                label=str(item_number),
                emoji="✏️",
                style=discord.ButtonStyle.secondary,
                row=1,
                disabled=not has_timer,
            )

            async def _edit_callback(
                interaction: discord.Interaction,
                timer_index: int = index,
            ) -> None:
                await self._edit_timer(interaction, timer_index)

            edit_button.callback = _edit_callback
            self.add_item(edit_button)

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
            await interaction.followup.send(ephemeral=True, content=message)
            return
        await interaction.response.send_message(ephemeral=True, content=message)

    @staticmethod
    def _extract_start_params(timer_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "workspace_id": timer_data.get("workspace_id") or timer_data.get("wid"),
            "billable": timer_data.get("billable"),
            "description": timer_data.get("description"),
            "pid": timer_data.get("project_id") or timer_data.get("pid"),
            "tags": timer_data.get("tags") or [],
            "tid": timer_data.get("task_id") or timer_data.get("tid"),
        }

    async def _reload_history_payload(self) -> dict:
        from embeds.TogglEmbeds import TogglEmbeds

        payload = await asyncio.to_thread(
            TogglEmbeds.timerhistory_embed,
            self.limit,
            self.guild_id,
            self.user_id,
        )
        history_view_data = payload.pop("_toggl_timer_history_view", None)
        if history_view_data is None:
            self.timers = []
            self.clear_items()
            payload["view"] = None
            return payload

        self.timers = [
            dict(timer or {}) for timer in (history_view_data.get("timers") or [])
        ][: self.limit]
        self._build()
        payload["view"] = self
        return payload

    async def _refresh_history_message(
        self,
        source_message: Optional[discord.Message],
    ) -> None:
        if source_message is None:
            return

        payload = await self._reload_history_payload()
        try:
            await source_message.edit(**payload)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

    async def _start_timer(
        self,
        interaction: discord.Interaction,
        timer_index: int,
    ) -> None:
        from embeds.TogglEmbeds import TogglEmbeds
        from views.TogglTimerView import TogglTimerView

        if timer_index >= len(self.timers):
            await interaction.response.defer(ephemeral=True)
            return

        timer_data = self.timers[timer_index]

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
            current_timer = await asyncio.to_thread(toggl.getCurrentTimeEntry)
            if current_timer is not None:
                embed = await asyncio.to_thread(
                    TogglEmbeds._single_timer_embed,
                    title=":stopwatch: Toggl Start Timer",
                    toggl=toggl,
                    timer_data=current_timer,
                    description=(
                        "A Toggl timer is already running. "
                        "Use `/toggl timer stop` to end it, then try again."
                    ),
                    color="#c96a40",
                )
                await interaction.response.edit_message(
                    embeds=[embed],
                    view=TogglTimerView(
                        guild_id=self.guild_id,
                        user_id=self.user_id,
                        timer_data=current_timer,
                        is_active=True,
                    ),
                )
                return

            start_params = self._extract_start_params(timer_data)
            if start_params.get("workspace_id") is None:
                await self._send_error(
                    interaction,
                    "This timer does not include enough data to start again.",
                )
                return

            started_timer = await asyncio.to_thread(
                toggl.startCurrentTimeEntry,
                **start_params,
            )
            if not isinstance(started_timer, dict) or started_timer.get("id") is None:
                await self._send_error(
                    interaction,
                    "Toggl rejected that timer start request.",
                )
                return

            embed = await asyncio.to_thread(
                TogglEmbeds._single_timer_embed,
                title=":stopwatch: Toggl Start Timer",
                toggl=toggl,
                timer_data=started_timer,
            )
            await interaction.response.edit_message(
                embeds=[embed],
                view=TogglTimerView(
                    guild_id=self.guild_id,
                    user_id=self.user_id,
                    timer_data=started_timer,
                    is_active=True,
                ),
            )
        except Exception:
            await self._send_error(
                interaction,
                "I couldn't update that Toggl timer right now. Please try again.",
            )

    async def _edit_timer(
        self,
        interaction: discord.Interaction,
        timer_index: int,
    ) -> None:
        if timer_index >= len(self.timers):
            await interaction.response.defer(ephemeral=True)
            return

        timer_data = self.timers[timer_index]

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

        workspace_id = timer_data.get("workspace_id") or timer_data.get("wid")
        time_entry_id = timer_data.get("id")
        if workspace_id is None or time_entry_id is None:
            await self._send_error(
                interaction,
                "This timer does not include enough data to edit.",
            )
            return

        source_message = interaction.message
        try:
            form_options = await asyncio.to_thread(
                TogglTimeEntryEditModal.build_form_options,
                toggl,
                timer_data,
            )
        except Exception:
            await self._send_error(
                interaction,
                "I couldn't load that timer editor right now. Please try again.",
            )
            return

        async def on_saved(
            modal_interaction: discord.Interaction,
            updated_timer: dict[str, Any],
        ) -> None:
            self.timers[timer_index] = dict(updated_timer or {})
            await self._refresh_history_message(source_message)
            await modal_interaction.followup.send(
                ephemeral=True,
                content="Timer updated.",
            )

        await interaction.response.send_modal(
            TogglTimeEntryEditModal(
                toggl=toggl,
                timer_data=timer_data,
                project_options=form_options["project_options"],
                tag_options=form_options["tag_options"],
                tags_disabled=form_options["tags_disabled"],
                on_saved=on_saved,
            )
        )
