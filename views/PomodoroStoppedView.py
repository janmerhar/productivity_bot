from typing import Optional

import discord

from views.PomodoroStartView import PomodoroVoiceChannelSelectView
from views.pomodoro_dynamic_items import (
    PomodoroStoppedBreakButton,
    PomodoroStoppedCustomTimerButton,
    PomodoroStoppedFocusButton,
    _ensure_stopped_owner,
    _send_started_pomodoro,
)

_POMODORO_STOP_MODAL_SELECTS_SUPPORTED = True


def build_custom_voice_options(
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


class PomodoroCustomTimerModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        user_id: int,
        source_message: Optional[discord.Message],
        voice_options: list[discord.SelectOption],
    ) -> None:
        super().__init__(title="Start Custom Pomodoro")
        self._user_id = user_id
        self._source_message = source_message
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
        if not await _ensure_stopped_owner(interaction, self._user_id):
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
            except ValueError:
                await interaction.response.send_message(
                    ephemeral=False,
                    content="Duration must be a whole number of minutes.",
                )
                return
            if duration_value <= 0:
                await interaction.response.send_message(
                    ephemeral=False,
                    content="Duration must be greater than zero.",
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
                await interaction.response.send_message(
                    ephemeral=False,
                    content="Voice channel selection isn't available in DMs.",
                )
                return
            target_channel = PomodoroVoiceChannelSelectView._resolve_selected_voice_channel(
                interaction.guild,
                voice_selection,
            )
            if target_channel is None:
                await interaction.response.send_message(
                    ephemeral=False,
                    content="That voice channel was not found.",
                )
                return
            use_member_voice = False
            skip_voice = False

        await interaction.response.defer(ephemeral=False)

        await _send_started_pomodoro(
            interaction,
            mode=mode,
            duration=duration_value,
            target_channel=target_channel,
            use_member_voice=use_member_voice,
            skip_voice=skip_voice,
            source_message=self._source_message,
            source_disabled_view=PomodoroStoppedView(self._user_id, disabled=True),
        )


class PomodoroStoppedView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        *,
        disabled: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.add_item(PomodoroStoppedFocusButton(user_id, disabled=disabled))
        self.add_item(PomodoroStoppedBreakButton(user_id, disabled=disabled))
        self.add_item(PomodoroStoppedCustomTimerButton(user_id, disabled=disabled))
