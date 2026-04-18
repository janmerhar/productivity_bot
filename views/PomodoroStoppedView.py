# PomodoroStoppedView.py

import asyncio
from typing import Optional

import discord

from classes.PomodoroFunctions import PomodoroFunctions
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from embeds.PomodoroEmbeds import PomodoroEmbeds
from services.error_reporting import (
    ValidationError,
    UserVisibleError,
    handle_interaction_error,
)
from views.PomodoroStartView import PomodoroStartView, PomodoroVoiceChannelSelectView

_POMODORO_STOP_MODAL_SELECTS_SUPPORTED = True


class PomodoroCustomTimerModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        parent_view: "PomodoroStoppedView",
        voice_options: list[discord.SelectOption],
    ) -> None:
        super().__init__(title="Start Custom Pomodoro")
        self._parent_view = parent_view
        self.mode_select = discord.ui.Select(
            placeholder="Mode",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Focus", value="focus", default=True),
                discord.SelectOption(label="Break", value="break"),
            ],
        )
        self.mode_select_label = discord.ui.Label(
            text="Mode",
            component=self.mode_select,
        )
        self.add_item(self.mode_select_label)
        self.duration_input = discord.ui.TextInput(
            label="Duration (minutes, optional)",
            placeholder="Defaults: 30 focus / 5 break",
            required=False,
            max_length=4,
        )
        self.add_item(self.duration_input)

        self.voice_select = discord.ui.Select(
            placeholder="Voice channel",
            min_values=1,
            max_values=1,
            options=voice_options[:25],
        )
        self.voice_select_label = discord.ui.Label(
            text="Voice playback",
            component=self.voice_select,
        )
        self.add_item(self.voice_select_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self._parent_view._ensure_user(interaction):
            return

        mode = (
            self.mode_select.values[0].strip().lower()
            if self.mode_select.values
            else "focus"
        )
        if mode not in ("focus", "break"):
            mode = "focus"

        duration_value: Optional[int] = None
        raw_duration = (self.duration_input.value or "").strip()
        if raw_duration:
            try:
                duration_value = int(raw_duration)
            except ValueError as exc:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Duration must be a whole number of minutes.",
                        ephemeral=False,
                        cause=exc,
                    ),
                )
                return
            if duration_value <= 0:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Duration must be greater than zero.",
                        ephemeral=False,
                    ),
                )
                return

        voice_selection = (
            self.voice_select.values[0] if self.voice_select.values else "__auto__"
        )
        if voice_selection == "__auto__":
            target_channel = None
            use_member_voice = True
            skip_voice = False
        elif voice_selection == "__none__":
            target_channel = None
            use_member_voice = False
            skip_voice = True
        else:
            if interaction.guild is None:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Voice channel selection isn't available in DMs.",
                        ephemeral=False,
                    ),
                )
                return
            target_channel = (
                PomodoroVoiceChannelSelectView._resolve_selected_voice_channel(
                    interaction.guild,
                    voice_selection,
                )
            )
            if target_channel is None:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "That voice channel was not found.",
                        ephemeral=False,
                    ),
                )
                return
            use_member_voice = False
            skip_voice = False

        await self._parent_view._start_with_options(
            interaction,
            mode=mode,
            duration=duration_value,
            target_channel=target_channel,
            use_member_voice=use_member_voice,
            skip_voice=skip_voice,
        )


class PomodoroStoppedView(discord.ui.View):
    def __init__(self, user_id: int, *, timeout: float = 21600) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id

    async def _ensure_user(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self._user_id:
            return True
        await interaction.response.send_message(
            ephemeral=False,
            content="Only the user who stopped this pomodoro can do this.",
        )
        return False

    @staticmethod
    def _custom_voice_options(
        interaction: discord.Interaction,
    ) -> list[discord.SelectOption]:
        options: list[discord.SelectOption] = [
            discord.SelectOption(
                label="Auto (your current voice channel)",
                value="__auto__",
                default=True,
            )
        ]
        if interaction.guild is not None:
            for option in PomodoroVoiceChannelSelectView._build_voice_channel_options(
                interaction
            ):
                if not option.value.startswith("voice:"):
                    continue
                options.append(
                    discord.SelectOption(
                        label=option.label,
                        value=option.value,
                    )
                )
                if len(options) >= 24:
                    break

        options.append(
            discord.SelectOption(
                label="No voice playback",
                value="__none__",
            )
        )
        return options

    async def _start_with_options(
        self,
        interaction: discord.Interaction,
        *,
        mode: str,
        duration: Optional[int],
        target_channel: Optional[discord.VoiceChannel],
        use_member_voice: bool,
        skip_voice: bool,
    ) -> None:
        if not await self._ensure_user(interaction):
            return

        await interaction.response.defer(ephemeral=False)

        try:
            end_time, resolved_duration = await asyncio.to_thread(
                PomodoroFunctions.create_timer,
                interaction.guild_id,
                interaction.channel_id,
                mode,
                duration,
                interaction.user.id,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    str(exc),
                    ephemeral=False,
                    cause=exc,
                ),
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while starting that pomodoro.",
                    ephemeral=False,
                    cause=exc,
                ),
            )
            return

        voice_error: Optional[str] = None
        resolved_target_channel = target_channel

        if skip_voice:
            voice_error = None
        elif interaction.guild is None:
            voice_error = None
        else:
            member = interaction.user
            if resolved_target_channel is None and use_member_voice:
                if isinstance(member, discord.Member) and member.voice:
                    resolved_target_channel = member.voice.channel

            if resolved_target_channel is None:
                voice_error = "Join a voice channel so I can play audio."
            else:
                voice_error = await PomodoroVoiceManager.start_session(
                    interaction.guild,
                    resolved_target_channel,
                    end_time,
                    mode,
                )

        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            resolved_duration,
            end_time,
        )
        join_url = resolved_target_channel.jump_url if resolved_target_channel else None
        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url if voice_error is None else None,
            mode=mode,
            end_time=end_time,
            voice_channel_select_enabled=interaction.guild is not None,
        )
        payload["content"] = voice_error or None

        try:
            if interaction.message is not None:
                await interaction.message.edit(**payload)
            else:
                await interaction.followup.send(ephemeral=False, **payload)
        except discord.HTTPException:
            await interaction.followup.send(ephemeral=False, **payload)

    @discord.ui.button(label="Start Focus", style=discord.ButtonStyle.success)
    async def start_focus(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._start_with_options(
            interaction,
            mode="focus",
            duration=None,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
        )

    @discord.ui.button(label="Start Break", style=discord.ButtonStyle.primary)
    async def start_break(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._start_with_options(
            interaction,
            mode="break",
            duration=None,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
        )

    @discord.ui.button(label="Custom Timer", style=discord.ButtonStyle.secondary)
    async def custom_timer(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if not await self._ensure_user(interaction):
            return

        global _POMODORO_STOP_MODAL_SELECTS_SUPPORTED
        voice_options = self._custom_voice_options(interaction)

        if _POMODORO_STOP_MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    PomodoroCustomTimerModal(
                        parent_view=self,
                        voice_options=voice_options,
                    )
                )
                return
            except discord.HTTPException as exc:
                if exc.code == 50035 and "must be one of (4,)" in str(exc):
                    _POMODORO_STOP_MODAL_SELECTS_SUPPORTED = False
                else:
                    raise

        await interaction.response.send_message(
            ephemeral=False,
            content=(
                "Custom timer popup with dropdowns is not supported here. "
                "Use `/pomodoro start` for custom mode, duration, and voice options."
            ),
        )
