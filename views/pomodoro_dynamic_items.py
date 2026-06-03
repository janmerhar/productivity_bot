import asyncio
import datetime
from typing import Optional

import discord
from discord.ext import commands

from classes.PomodoroFunctions import PomodoroFunctions
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from embeds.PomodoroEmbeds import PomodoroEmbeds
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)
from services.visibility import inherit_ephemeral_from_interaction


async def register_pomodoro_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        PomodoroRestartFocusButton,
        PomodoroRestartBreakButton,
        PomodoroStartSelectVoiceButton,
        PomodoroStartPlayPauseButton,
        PomodoroStartExtendButton,
        PomodoroStartAutoCycleButton,
        PomodoroStartStopButton,
        PomodoroStoppedFocusButton,
        PomodoroStoppedBreakButton,
        PomodoroStoppedCustomTimerButton,
    )


def _current_join_url(interaction: discord.Interaction) -> Optional[str]:
    if interaction.guild is None:
        return None

    session = PomodoroVoiceManager.sessions.get(interaction.guild.id)
    if session is None:
        return None

    channel = interaction.guild.get_channel(session.voice_channel_id)
    if not isinstance(channel, discord.VoiceChannel):
        return None
    return channel.jump_url


def _optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "x":
        return None
    return int(value)


def _encode_optional_int(value: Optional[int]) -> str:
    return "x" if value is None else str(value)


async def _ensure_owner(
    interaction: discord.Interaction,
    user_id: int,
    *,
    response_ephemeral: bool,
) -> bool:
    if interaction.user.id == user_id:
        return True

    await interaction.response.send_message(
        ephemeral=response_ephemeral,
        content="Only the user who started this pomodoro can do this.",
    )
    return False


async def _ensure_stopped_owner(
    interaction: discord.Interaction,
    user_id: int,
    *,
    response_ephemeral: bool,
) -> bool:
    if interaction.user.id == user_id:
        return True

    await interaction.response.send_message(
        ephemeral=response_ephemeral,
        content="Only the user who stopped this pomodoro can do this.",
    )
    return False


async def _disable_source_message(
    source_message: Optional[discord.Message],
    view: Optional[discord.ui.View],
) -> None:
    if source_message is None:
        return
    try:
        await source_message.edit(view=view)
    except discord.HTTPException:
        pass


async def _send_started_pomodoro(
    interaction: discord.Interaction,
    *,
    mode: str,
    duration: Optional[int],
    focus_duration: Optional[int] = None,
    break_duration: Optional[int] = None,
    streak: int = 0,
    target_channel: Optional[discord.VoiceChannel],
    use_member_voice: bool,
    skip_voice: bool,
    source_message: Optional[discord.Message] = None,
    source_disabled_view: Optional[discord.ui.View] = None,
    response_ephemeral: bool,
) -> None:
    from views.PomodoroStartView import PomodoroStartView

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
            streak,
        )
    except ValueError as exc:
        await handle_interaction_error(
            interaction,
            ValidationError(
                str(exc),
                ephemeral=response_ephemeral,
                cause=exc,
            ),
        )
        return
    except Exception as exc:
        await handle_interaction_error(
            interaction,
            UserVisibleError(
                "Something went wrong while starting that pomodoro.",
                ephemeral=response_ephemeral,
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
        focus_duration=focus_duration,
        break_duration=break_duration,
        streak=PomodoroFunctions._safe_int(
            (created_job.data or {}).get("streak"), default=streak
        ),
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
        streak=PomodoroFunctions._safe_int(
            (created_job.data or {}).get("streak"), default=streak
        ),
    )
    payload["content"] = voice_error or None

    posted_message: Optional[discord.Message] = None
    try:
        if source_message is not None and not response_ephemeral:
            await source_message.edit(**payload)
            posted_message = source_message
        else:
            posted_message = await interaction.followup.send(
                ephemeral=response_ephemeral,
                wait=True,
                **payload,
            )
    except discord.HTTPException:
        posted_message = await interaction.followup.send(
            ephemeral=response_ephemeral,
            wait=True,
            **payload,
        )

    if posted_message is not None and not response_ephemeral:
        await PomodoroFunctions.bind_timer_message(
            job_id=str(created_job.id),
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            message_id=posted_message.id,
        )

    if source_disabled_view is not None and (
        posted_message is None or posted_message.id != getattr(source_message, "id", 0)
    ):
        await _disable_source_message(source_message, source_disabled_view)


class PomodoroRestartFocusButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"pomodoro:restart:focus"
        r"(?::(?P<user_id>\d+):(?P<focus>x|\d+):(?P<break_duration>x|\d+):"
        r"(?P<streak>\d+):(?P<expires>\d+))?"
    ),
):
    def __init__(
        self,
        *,
        user_id: int = 0,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
        chain_expires_at: Optional[datetime.datetime] = None,
        disabled: bool = False,
    ) -> None:
        custom_id = "pomodoro:restart:focus"
        if user_id or focus_duration is not None or break_duration is not None or streak:
            expires = int(chain_expires_at.timestamp()) if chain_expires_at else 0
            custom_id = (
                "pomodoro:restart:focus:"
                f"{user_id}:{_encode_optional_int(focus_duration)}:"
                f"{_encode_optional_int(break_duration)}:{streak}:{expires}"
            )
        super().__init__(
            discord.ui.Button(
                label="Start Focus",
                style=discord.ButtonStyle.success,
                custom_id=custom_id,
                disabled=disabled,
            )
        )
        self.user_id = user_id
        self.focus_duration = focus_duration
        self.break_duration = break_duration
        self.streak = streak
        self.chain_expires_at = chain_expires_at

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroRestartFocusButton":
        del interaction
        expires_raw = match.groupdict().get("expires")
        expires = (
            datetime.datetime.fromtimestamp(int(expires_raw))
            if expires_raw and expires_raw != "0"
            else None
        )
        return cls(
            user_id=int(match.groupdict().get("user_id") or 0),
            focus_duration=_optional_int(match.groupdict().get("focus")),
            break_duration=_optional_int(match.groupdict().get("break_duration")),
            streak=int(match.groupdict().get("streak") or 0),
            chain_expires_at=expires,
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroRestartView import PomodoroRestartView

        response_ephemeral = inherit_ephemeral_from_interaction(interaction)
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content="Only the user who completed this pomodoro can do this.",
            )
            return
        await interaction.response.defer(ephemeral=response_ephemeral)
        streak = self.streak
        if self.chain_expires_at is not None and datetime.datetime.now() > self.chain_expires_at:
            streak = 0
        await _send_started_pomodoro(
            interaction,
            mode="focus",
            duration=self.focus_duration,
            focus_duration=self.focus_duration,
            break_duration=self.break_duration,
            streak=streak,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroRestartView(
                user_id=self.user_id,
                focus_duration=self.focus_duration,
                break_duration=self.break_duration,
                streak=streak,
                chain_expires_at=self.chain_expires_at,
                disabled=True,
            ),
            response_ephemeral=response_ephemeral,
        )


class PomodoroRestartBreakButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"pomodoro:restart:break"
        r"(?::(?P<user_id>\d+):(?P<focus>x|\d+):(?P<break_duration>x|\d+):"
        r"(?P<streak>\d+):(?P<expires>\d+))?"
    ),
):
    def __init__(
        self,
        *,
        user_id: int = 0,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
        chain_expires_at: Optional[datetime.datetime] = None,
        disabled: bool = False,
    ) -> None:
        custom_id = "pomodoro:restart:break"
        if user_id or focus_duration is not None or break_duration is not None or streak:
            expires = int(chain_expires_at.timestamp()) if chain_expires_at else 0
            custom_id = (
                "pomodoro:restart:break:"
                f"{user_id}:{_encode_optional_int(focus_duration)}:"
                f"{_encode_optional_int(break_duration)}:{streak}:{expires}"
            )
        super().__init__(
            discord.ui.Button(
                label="Start Relax",
                style=discord.ButtonStyle.secondary,
                custom_id=custom_id,
                disabled=disabled,
            )
        )
        self.user_id = user_id
        self.focus_duration = focus_duration
        self.break_duration = break_duration
        self.streak = streak
        self.chain_expires_at = chain_expires_at

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroRestartBreakButton":
        del interaction
        expires_raw = match.groupdict().get("expires")
        expires = (
            datetime.datetime.fromtimestamp(int(expires_raw))
            if expires_raw and expires_raw != "0"
            else None
        )
        return cls(
            user_id=int(match.groupdict().get("user_id") or 0),
            focus_duration=_optional_int(match.groupdict().get("focus")),
            break_duration=_optional_int(match.groupdict().get("break_duration")),
            streak=int(match.groupdict().get("streak") or 0),
            chain_expires_at=expires,
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroRestartView import PomodoroRestartView

        response_ephemeral = inherit_ephemeral_from_interaction(interaction)
        if self.user_id and interaction.user.id != self.user_id:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content="Only the user who completed this pomodoro can do this.",
            )
            return
        await interaction.response.defer(ephemeral=response_ephemeral)
        streak = self.streak
        if self.chain_expires_at is not None and datetime.datetime.now() > self.chain_expires_at:
            streak = 0
        await _send_started_pomodoro(
            interaction,
            mode="break",
            duration=self.break_duration,
            focus_duration=self.focus_duration,
            break_duration=self.break_duration,
            streak=streak,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroRestartView(
                user_id=self.user_id,
                focus_duration=self.focus_duration,
                break_duration=self.break_duration,
                streak=streak,
                chain_expires_at=self.chain_expires_at,
                disabled=True,
            ),
            response_ephemeral=response_ephemeral,
        )


class PomodoroStartSelectVoiceButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:start:voice:(?P<user_id>\d+)",
):
    def __init__(
        self,
        user_id: int,
        *,
        disabled: bool = False,
        server_only: bool = False,
    ) -> None:
        label = "Select Voice Channel (Server only)" if server_only else "Select Voice Channel"
        style = (
            discord.ButtonStyle.secondary if server_only else discord.ButtonStyle.primary
        )
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,
                custom_id=f"pomodoro:start:voice:{user_id}",
                disabled=disabled,
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStartSelectVoiceButton":
        del interaction
        label = getattr(item, "label", "") or ""
        server_only = "server only" in label.lower()
        return cls(
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
            server_only=server_only,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStartView import (
            PomodoroVoiceChannelSelectModal,
            PomodoroVoiceChannelSelectView,
        )
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content="Voice channel selection isn't available in DMs.",
            )
            return

        state = await PomodoroFunctions.get_user_pomodoro_state(interaction)
        if not state.exists:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )
            return

        voice_channel_options = PomodoroVoiceChannelSelectView._build_voice_channel_options(
            interaction
        )
        if not voice_channel_options:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content="No available voice channels found.",
            )
            return

        import views.PomodoroStartView as start_view_module

        if start_view_module._POMODORO_MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    PomodoroVoiceChannelSelectModal(
                        user_id=self.user_id,
                        mode=state.mode,
                        end_time=state.end_time,
                        voice_channel_options=voice_channel_options,
                        response_ephemeral=response_ephemeral,
                    )
                )
                return
            except discord.HTTPException as exc:
                if exc.code == 50035 and "must be one of (4,)" in str(exc):
                    start_view_module._POMODORO_MODAL_SELECTS_SUPPORTED = False
                else:
                    raise

        picker_view = PomodoroVoiceChannelSelectView(
            interaction=interaction,
            user_id=self.user_id,
            mode=state.mode,
            end_time=state.end_time,
            response_ephemeral=response_ephemeral,
        )
        await interaction.response.send_message(
            ephemeral=response_ephemeral,
            content="Choose a voice channel:",
            view=picker_view,
        )


class PomodoroStartPlayPauseButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:start:toggle:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int, *, paused: bool = False, disabled: bool = False) -> None:
        label = "Resume" if paused else "Pause"
        emoji = "▶️" if paused else "⏸️"
        style = (
            discord.ButtonStyle.success if paused else discord.ButtonStyle.secondary
        )
        super().__init__(
            discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=f"pomodoro:start:toggle:{user_id}",
                disabled=disabled,
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStartPlayPauseButton":
        del interaction
        label = getattr(item, "label", "") or ""
        paused = label.lower() == "resume"
        return cls(
            int(match.group("user_id")),
            paused=paused,
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStartView import PomodoroStartView
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        state = await PomodoroFunctions.get_user_pomodoro_state(interaction)
        if not state.exists:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )
            return

        if state.is_paused:
            result = await PomodoroFunctions.resume_user_pomodoro(interaction)
            if not result.ok or result.end_time is None or result.duration_minutes is None:
                await interaction.response.send_message(
                    ephemeral=response_ephemeral,
                    content=result.message,
                )
                return

            mode = result.mode or state.mode
            updated_embed = PomodoroStartView._with_resumed_timer_fields(
                (
                    interaction.message.embeds[0]
                    if interaction.message and interaction.message.embeds
                    else None
                ),
                mode,
                result.end_time,
                result.duration_minutes,
                state.focus_duration,
                state.break_duration,
                state.streak,
            )
            if updated_embed is None:
                await interaction.response.send_message(
                    ephemeral=response_ephemeral,
                    content=(
                        "Pomodoro resumed, but I couldn't refresh the timer card. "
                        f"New end: {PomodoroStartView._relative_timestamp(result.end_time)}"
                    ),
                )
                return

            await interaction.response.edit_message(
                embed=updated_embed,
                view=PomodoroStartView(
                    self.user_id,
                    join_url=_current_join_url(interaction),
                    mode=mode,
                    end_time=result.end_time,
                    is_paused=False,
                    auto_cycle_enabled=state.auto_cycle_enabled,
                    voice_channel_select_enabled=interaction.guild is not None,
                    focus_duration=state.focus_duration,
                    break_duration=state.break_duration,
                    streak=state.streak,
                ),
            )
            return

        result = await PomodoroFunctions.pause_user_pomodoro(interaction)
        if not result.ok:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=result.message,
            )
            return

        remaining_minutes = result.remaining_minutes or 1
        mode = result.mode or state.mode
        updated_embed = PomodoroStartView._with_paused_timer_fields(
            (
                interaction.message.embeds[0]
                if interaction.message and interaction.message.embeds
                else None
            ),
            mode,
            remaining_minutes,
            result.remaining_seconds,
            state.focus_duration,
            state.break_duration,
            state.streak,
        )
        if updated_embed is None:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=f"Paused with {remaining_minutes} minute(s) remaining.",
            )
            return

        await interaction.response.edit_message(
            embed=updated_embed,
            view=PomodoroStartView(
                self.user_id,
                join_url=_current_join_url(interaction),
                mode=mode,
                end_time=None,
                is_paused=True,
                auto_cycle_enabled=state.auto_cycle_enabled,
                voice_channel_select_enabled=interaction.guild is not None,
                focus_duration=state.focus_duration,
                break_duration=state.break_duration,
                streak=state.streak,
            ),
        )


class PomodoroStartExtendButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:start:extend:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Extend +5 min",
                style=discord.ButtonStyle.secondary,
                custom_id=f"pomodoro:start:extend:{user_id}",
                disabled=disabled,
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStartExtendButton":
        del interaction
        return cls(
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStartView import PomodoroStartView
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        state = await PomodoroFunctions.get_user_pomodoro_state(interaction)
        if not state.exists:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )
            return

        if state.is_paused:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content="Resume the pomodoro before extending it.",
            )
            return

        result = await PomodoroFunctions.extend_user_pomodoro(
            interaction,
            minutes=5,
            expected_end_time=state.end_time,
        )
        if not result.ok or result.end_time is None or result.duration_minutes is None:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=result.message,
            )
            return

        updated_embed = PomodoroStartView._with_updated_timer_fields(
            (
                interaction.message.embeds[0]
                if interaction.message and interaction.message.embeds
                else None
            ),
            result.end_time,
            result.duration_minutes,
            state.focus_duration,
            state.break_duration,
            state.streak,
        )
        if updated_embed is None:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=(
                    "Extended by 5 minutes, but I couldn't refresh the timer card. "
                    f"New end: {PomodoroStartView._relative_timestamp(result.end_time)}"
                ),
            )
            return

        try:
            await interaction.response.edit_message(
                embed=updated_embed,
                view=PomodoroStartView(
                    self.user_id,
                    join_url=_current_join_url(interaction),
                    mode=result.mode or state.mode,
                    end_time=result.end_time,
                    is_paused=False,
                    auto_cycle_enabled=state.auto_cycle_enabled,
                    voice_channel_select_enabled=interaction.guild is not None,
                    focus_duration=state.focus_duration,
                    break_duration=state.break_duration,
                    streak=state.streak,
                ),
            )
        except discord.HTTPException:
            fallback_message = (
                "Extended by 5 minutes, but that timer message no longer exists. "
                f"New end: {PomodoroStartView._relative_timestamp(result.end_time)}"
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    ephemeral=response_ephemeral,
                    content=fallback_message,
                )
            else:
                await interaction.response.send_message(
                    ephemeral=response_ephemeral,
                    content=fallback_message,
                )


class PomodoroStartAutoCycleButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:start:auto:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int, *, enabled: bool = False, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Auto On" if enabled else "Auto Off",
                style=discord.ButtonStyle.success if enabled else discord.ButtonStyle.secondary,
                custom_id=f"pomodoro:start:auto:{user_id}",
                disabled=disabled,
            )
        )
        self.user_id = user_id
        self.enabled = enabled

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStartAutoCycleButton":
        del interaction
        label = getattr(item, "label", "") or ""
        return cls(
            int(match.group("user_id")),
            enabled=label.lower() == "auto on",
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStartView import PomodoroStartView
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        state = await PomodoroFunctions.get_user_pomodoro_state(interaction)
        if not state.exists:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )
            return

        ok, enabled, message = await PomodoroFunctions.toggle_auto_cycle(
            interaction,
            expected_end_time=state.end_time,
            is_paused=state.is_paused,
        )
        if not ok or enabled is None:
            await interaction.response.send_message(
                ephemeral=response_ephemeral,
                content=message,
            )
            return

        await interaction.response.edit_message(
            view=PomodoroStartView(
                self.user_id,
                join_url=_current_join_url(interaction),
                mode=state.mode,
                end_time=state.end_time,
                is_paused=state.is_paused,
                auto_cycle_enabled=enabled,
                voice_channel_select_enabled=interaction.guild is not None,
                focus_duration=state.focus_duration,
                break_duration=state.break_duration,
                streak=state.streak,
            ),
        )


class PomodoroStartStopButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:start:stop:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Stop Pomodoro",
                style=discord.ButtonStyle.danger,
                custom_id=f"pomodoro:start:stop:{user_id}",
                disabled=disabled,
            )
        )
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStartStopButton":
        del interaction
        return cls(
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStoppedView import PomodoroStoppedView
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        await interaction.response.defer(ephemeral=response_ephemeral)
        result = await PomodoroFunctions.stop_user_pomodoro(interaction)
        if not result.ok:
            await interaction.followup.send(
                ephemeral=response_ephemeral,
                content=result.message,
            )
            return

        best_streak = await asyncio.to_thread(
            PomodoroFunctions.fetch_best_pomodoro_streak,
            interaction.user.id,
        )
        payload = PomodoroEmbeds.timer_stopped_embed(
            streak=result.streak,
            best_streak=best_streak,
            focus_duration=result.focus_duration,
            break_duration=result.break_duration,
        )
        payload["content"] = None
        stopped_view = PomodoroStoppedView(
            interaction.user.id,
            focus_duration=result.focus_duration,
            break_duration=result.break_duration,
        )
        if interaction.message is not None:
            await _disable_source_message(interaction.message, view=None)

        await interaction.followup.send(
            ephemeral=response_ephemeral,
            **payload,
            view=stopped_view,
        )


class PomodoroStoppedFocusButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:stopped:focus:(?P<user_id>\d+)(?::(?P<focus>x|\d+):(?P<break_duration>x|\d+))?",
):
    def __init__(
        self,
        user_id: int,
        *,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        disabled: bool = False,
    ) -> None:
        suffix = ""
        if focus_duration is not None or break_duration is not None:
            suffix = f":{_encode_optional_int(focus_duration)}:{_encode_optional_int(break_duration)}"
        super().__init__(
            discord.ui.Button(
                label="Start Focus",
                style=discord.ButtonStyle.success,
                custom_id=f"pomodoro:stopped:focus:{user_id}{suffix}",
                disabled=disabled,
            )
        )
        self.user_id = user_id
        self.focus_duration = focus_duration
        self.break_duration = break_duration

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStoppedFocusButton":
        del interaction
        return cls(
            int(match.group("user_id")),
            focus_duration=_optional_int(match.groupdict().get("focus")),
            break_duration=_optional_int(match.groupdict().get("break_duration")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStoppedView import PomodoroStoppedView
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_stopped_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        await interaction.response.defer(ephemeral=response_ephemeral)
        await _send_started_pomodoro(
            interaction,
            mode="focus",
            duration=self.focus_duration,
            focus_duration=self.focus_duration,
            break_duration=self.break_duration,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroStoppedView(
                self.user_id,
                focus_duration=self.focus_duration,
                break_duration=self.break_duration,
                disabled=True,
            ),
            response_ephemeral=response_ephemeral,
        )


class PomodoroStoppedBreakButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:stopped:break:(?P<user_id>\d+)(?::(?P<focus>x|\d+):(?P<break_duration>x|\d+))?",
):
    def __init__(
        self,
        user_id: int,
        *,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        disabled: bool = False,
    ) -> None:
        suffix = ""
        if focus_duration is not None or break_duration is not None:
            suffix = f":{_encode_optional_int(focus_duration)}:{_encode_optional_int(break_duration)}"
        super().__init__(
            discord.ui.Button(
                label="Start Break",
                style=discord.ButtonStyle.primary,
                custom_id=f"pomodoro:stopped:break:{user_id}{suffix}",
                disabled=disabled,
            )
        )
        self.user_id = user_id
        self.focus_duration = focus_duration
        self.break_duration = break_duration

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStoppedBreakButton":
        del interaction
        return cls(
            int(match.group("user_id")),
            focus_duration=_optional_int(match.groupdict().get("focus")),
            break_duration=_optional_int(match.groupdict().get("break_duration")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStoppedView import PomodoroStoppedView
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_stopped_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        await interaction.response.defer(ephemeral=response_ephemeral)
        await _send_started_pomodoro(
            interaction,
            mode="break",
            duration=self.break_duration,
            focus_duration=self.focus_duration,
            break_duration=self.break_duration,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroStoppedView(
                self.user_id,
                focus_duration=self.focus_duration,
                break_duration=self.break_duration,
                disabled=True,
            ),
            response_ephemeral=response_ephemeral,
        )


class PomodoroStoppedCustomTimerButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:stopped:custom:(?P<user_id>\d+)(?::(?P<focus>x|\d+):(?P<break_duration>x|\d+))?",
):
    def __init__(
        self,
        user_id: int,
        *,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        disabled: bool = False,
    ) -> None:
        suffix = ""
        if focus_duration is not None or break_duration is not None:
            suffix = f":{_encode_optional_int(focus_duration)}:{_encode_optional_int(break_duration)}"
        super().__init__(
            discord.ui.Button(
                label="Custom Timer",
                style=discord.ButtonStyle.secondary,
                custom_id=f"pomodoro:stopped:custom:{user_id}{suffix}",
                disabled=disabled,
            )
        )
        self.user_id = user_id
        self.focus_duration = focus_duration
        self.break_duration = break_duration

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroStoppedCustomTimerButton":
        del interaction
        return cls(
            int(match.group("user_id")),
            focus_duration=_optional_int(match.groupdict().get("focus")),
            break_duration=_optional_int(match.groupdict().get("break_duration")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroStoppedView import (
            PomodoroCustomTimerModal,
            build_custom_voice_options,
        )
        import views.PomodoroStoppedView as stopped_view_module
        response_ephemeral = inherit_ephemeral_from_interaction(interaction)

        if not await _ensure_stopped_owner(
            interaction,
            self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        voice_options = build_custom_voice_options(interaction)
        if stopped_view_module._POMODORO_STOP_MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    PomodoroCustomTimerModal(
                        user_id=self.user_id,
                        source_message=interaction.message,
                        voice_options=voice_options,
                        focus_duration=self.focus_duration,
                        break_duration=self.break_duration,
                        response_ephemeral=response_ephemeral,
                    )
                )
                return
            except discord.HTTPException as exc:
                if exc.code == 50035 and "must be one of (4,)" in str(exc):
                    stopped_view_module._POMODORO_STOP_MODAL_SELECTS_SUPPORTED = False
                else:
                    raise

        await interaction.response.send_message(
            ephemeral=response_ephemeral,
            content=(
                "Custom timer popup with dropdowns is not supported here. "
                "Use `/pomodoro start` for custom mode, duration, and voice options."
            ),
        )
