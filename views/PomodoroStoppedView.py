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
        interaction: discord.Interaction,
    ) -> None:
        super().__init__(title="Custom Pomodoro")
        self._parent_view = parent_view
        self.duration_input = discord.ui.TextInput(
            label="Focus Duration (min)",
            placeholder="30",
            required=False,
            max_length=4,
        )
        self.add_item(self.duration_input)
        self.break_duration_input = discord.ui.TextInput(
            label="Break Duration (min)",
            placeholder="5",
            required=False,
            max_length=4,
        )
        self.add_item(self.break_duration_input)

        default_values: list[discord.SelectDefaultValue] = []
        member = interaction.user
        if isinstance(member, discord.Member) and member.voice and isinstance(member.voice.channel, discord.VoiceChannel):
            default_values = [
                discord.SelectDefaultValue(
                    id=member.voice.channel.id,
                    type=discord.SelectDefaultValueType.channel,
                )
            ]

        self.voice_select = discord.ui.ChannelSelect(
            placeholder="None",
            channel_types=[discord.ChannelType.voice],
            min_values=0,
            max_values=1,
            default_values=default_values,
        )
        self.voice_select_label = discord.ui.Label(
            text="Voice playback",
            component=self.voice_select,
        )
        self.add_item(self.voice_select_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if not await self._parent_view._ensure_user(interaction):
            return

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

        break_duration_value: Optional[int] = None
        raw_break_duration = (self.break_duration_input.value or "").strip()
        if raw_break_duration:
            try:
                break_duration_value = int(raw_break_duration)
            except ValueError as exc:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Break duration must be a whole number of minutes.",
                        ephemeral=False,
                        cause=exc,
                    ),
                )
                return
            if break_duration_value <= 0:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Break duration must be greater than zero.",
                        ephemeral=False,
                    ),
                )
                return

        target_channel = None
        use_member_voice = True
        if self.voice_select.values:
            selected = self.voice_select.values[0]
            if interaction.guild is None:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Voice channel selection isn't available in DMs.",
                        ephemeral=False,
                    ),
                )
                return
            resolved = interaction.guild.get_channel(selected.id)
            if not isinstance(resolved, discord.VoiceChannel):
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "That voice channel was not found.",
                        ephemeral=False,
                    ),
                )
                return
            target_channel = resolved
            use_member_voice = False

        await self._parent_view._start_with_options(
            interaction,
            mode=mode,
            duration=duration_value,
            focus_duration=duration_value,
            break_duration=break_duration_value,
            target_channel=target_channel,
            use_member_voice=use_member_voice,
        )


class PomodoroStoppedView(discord.ui.View):
    def __init__(self, user_id: int, *, focus_duration: Optional[int] = None, break_duration: Optional[int] = None, timeout: float = 21600) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._focus_duration = focus_duration
        self._break_duration = break_duration

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
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        target_channel: Optional[discord.VoiceChannel],
        use_member_voice: bool,
    ) -> None:
        if not await self._ensure_user(interaction):
            return

        await interaction.response.defer(ephemeral=False)

        try:
            end_time, resolved_duration, created_job = await asyncio.to_thread(
                PomodoroFunctions.create_timer,
                interaction.guild_id,
                interaction.channel_id,
                mode,
                duration,
                interaction.user.id,
                break_duration,
                focus_duration,
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

        if interaction.guild is None:
            voice_error = None
        else:
            member = interaction.user
            if resolved_target_channel is None and use_member_voice:
                if isinstance(member, discord.Member) and member.voice:
                    resolved_target_channel = member.voice.channel

            if resolved_target_channel is None:
                voice_error = "Audio off — not in a voice channel."
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
            focus_duration=focus_duration,
            break_duration=break_duration,
        )
        join_url = resolved_target_channel.jump_url if resolved_target_channel else None
        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url if voice_error is None else None,
            mode=mode,
            end_time=end_time,
            voice_channel_select_enabled=interaction.guild is not None,
            focus_duration=focus_duration,
            break_duration=break_duration,
        )
        payload["content"] = voice_error or None

        try:
            if interaction.message is not None:
                await interaction.message.edit(**payload)
                posted_message = interaction.message
            else:
                posted_message = await interaction.followup.send(
                    ephemeral=False,
                    wait=True,
                    **payload,
                )
        except discord.HTTPException:
            posted_message = await interaction.followup.send(
                ephemeral=False,
                wait=True,
                **payload,
            )

        await PomodoroFunctions.bind_timer_message(
            job_id=str(created_job.id),
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            message_id=posted_message.id,
        )

    @discord.ui.button(label="Start Focus", style=discord.ButtonStyle.success, row=0)
    async def start_focus(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._start_with_options(
            interaction,
            mode="focus",
            duration=self._focus_duration,
            focus_duration=self._focus_duration,
            break_duration=self._break_duration,
            target_channel=None,
            use_member_voice=True,
        )

    @discord.ui.button(label="Start Break", style=discord.ButtonStyle.primary, row=0)
    async def start_break(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._start_with_options(
            interaction,
            mode="break",
            duration=self._break_duration,
            focus_duration=self._focus_duration,
            break_duration=self._break_duration,
            target_channel=None,
            use_member_voice=True,
        )

    @discord.ui.button(label="Custom Timer", style=discord.ButtonStyle.secondary, row=0)
    async def custom_timer(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if not await self._ensure_user(interaction):
            return

        global _POMODORO_STOP_MODAL_SELECTS_SUPPORTED

        if _POMODORO_STOP_MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    PomodoroCustomTimerModal(
                        parent_view=self,
                        interaction=interaction,
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
