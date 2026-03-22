import asyncio
from typing import Any, Optional

import discord

from classes.TogglFunctions import TogglFunctions
from classes.UserSettingsFunctions import UserSettingsFunctions


class TogglTimerView(discord.ui.View):
    STANDARD_FIELDS = {"description", "project", "billable", "start"}

    def __init__(
        self,
        guild_id: Optional[int],
        user_id: int,
        timer_data: dict[str, Any],
        is_active: bool,
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.guild_id = guild_id
        self.user_id = user_id
        self.timer_data = dict(timer_data or {})
        self.is_active = bool(is_active)
        self.is_terminal = False
        self._sync_button_state()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            ephemeral=True,
            content="Only the user who opened this Toggl timer can manage it.",
        )
        return False

    def _sync_button_state(self) -> None:
        self.play_pause_button.disabled = self.is_terminal
        self.stop_button.disabled = self.is_terminal or not self.is_active

        self.play_pause_button.label = None
        if self.is_active:
            self.play_pause_button.emoji = "⏸️"
            self.play_pause_button.style = discord.ButtonStyle.secondary
            return

        self.play_pause_button.emoji = "▶️"
        self.play_pause_button.style = discord.ButtonStyle.success

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
    def _preserve_extra_fields(
        source_embed: Optional[discord.Embed],
        target_embed: discord.Embed,
    ) -> discord.Embed:
        if source_embed is None:
            return target_embed

        for field in source_embed.fields:
            if (field.name or "").strip().lower() in TogglTimerView.STANDARD_FIELDS:
                continue
            target_embed.add_field(
                name=field.name,
                value=field.value,
                inline=field.inline,
            )

        return target_embed

    async def _render_message(
        self,
        interaction: discord.Interaction,
        *,
        title: str,
        description: Optional[str] = None,
        color: Optional[str] = None,
    ) -> None:
        from embeds.TogglEmbeds import TogglEmbeds

        toggl = self._get_toggl()
        if toggl is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="Your Toggl API key is missing.",
            )
            return

        current_embed = (
            interaction.message.embeds[0]
            if interaction.message and interaction.message.embeds
            else None
        )
        updated_embed = TogglEmbeds._single_timer_embed(
            title=title,
            toggl=toggl,
            timer_data=self.timer_data,
            description=description,
            color=color,
        )
        updated_embed = self._preserve_extra_fields(current_embed, updated_embed)
        await interaction.response.edit_message(embed=updated_embed, view=self)

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.secondary, row=0)
    async def play_pause_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
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
            if self.is_active:
                current_timer = await asyncio.to_thread(toggl.getCurrentTimeEntry)
                if current_timer is not None:
                    await asyncio.to_thread(toggl.stopCurrentTimeEntry)
                    self.timer_data = current_timer
                self.is_active = False
                self._sync_button_state()
                await self._render_message(
                    interaction,
                    title=":stopwatch: Toggl Timer Paused",
                    description=(
                        "Timer paused. Use ▶️ to start a new timer with the same details."
                    ),
                    color="#c96a40",
                )
                return

            current_timer = await asyncio.to_thread(toggl.getCurrentTimeEntry)
            if current_timer is not None:
                await self._send_error(
                    interaction,
                    "A Toggl timer is already running. Stop it before starting this one.",
                )
                return

            start_params = self._extract_start_params(self.timer_data)
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

            self.timer_data = started_timer
            self.is_active = True
            self.is_terminal = False
            self._sync_button_state()
            await self._render_message(
                interaction,
                title=":stopwatch: Toggl Timer Started",
                description="Timer started.",
            )
        except Exception:
            await self._send_error(
                interaction,
                "I couldn't update that Toggl timer right now. Please try again.",
            )

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, row=0)
    async def stop_button(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
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
                await asyncio.to_thread(toggl.stopCurrentTimeEntry)
                self.timer_data = current_timer

            self.is_active = False
            self.is_terminal = True
            self._sync_button_state()
            await self._render_message(
                interaction,
                title=":stopwatch: Toggl Timer Stopped",
                description="Timer stopped.",
                color="#552d4f",
            )
        except Exception:
            await self._send_error(
                interaction,
                "I couldn't stop that Toggl timer right now. Please try again.",
            )
