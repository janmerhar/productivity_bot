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
    view: discord.ui.View,
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
    target_channel: Optional[discord.VoiceChannel],
    use_member_voice: bool,
    skip_voice: bool,
    source_message: Optional[discord.Message] = None,
    source_disabled_view: Optional[discord.ui.View] = None,
    response_ephemeral: bool,
) -> None:
    from views.PomodoroStartView import PomodoroStartView

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
    )
    join_url = resolved_target_channel.jump_url if resolved_target_channel else None
    payload["view"] = PomodoroStartView(
        interaction.user.id,
        join_url=join_url if voice_error is None else None,
        mode=mode,
        end_time=end_time,
        voice_channel_select_enabled=interaction.guild is not None,
    )

    await interaction.followup.send(ephemeral=response_ephemeral, **payload)

    if voice_error:
        await interaction.followup.send(
            ephemeral=response_ephemeral,
            content=voice_error,
        )

    if source_disabled_view is not None:
        await _disable_source_message(source_message, source_disabled_view)


class PomodoroRestartFocusButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:restart:focus",
):
    def __init__(self, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Start Focus",
                style=discord.ButtonStyle.success,
                custom_id="pomodoro:restart:focus",
                disabled=disabled,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroRestartFocusButton":
        del interaction, match
        return cls(disabled=getattr(item, "disabled", False))

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroRestartView import PomodoroRestartView

        response_ephemeral = inherit_ephemeral_from_interaction(interaction)
        await interaction.response.defer(ephemeral=response_ephemeral)
        await _send_started_pomodoro(
            interaction,
            mode="focus",
            duration=None,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroRestartView(disabled=True),
            response_ephemeral=response_ephemeral,
        )


class PomodoroRestartBreakButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:restart:break",
):
    def __init__(self, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Start Relax",
                style=discord.ButtonStyle.secondary,
                custom_id="pomodoro:restart:break",
                disabled=disabled,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "PomodoroRestartBreakButton":
        del interaction, match
        return cls(disabled=getattr(item, "disabled", False))

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.PomodoroRestartView import PomodoroRestartView

        response_ephemeral = inherit_ephemeral_from_interaction(interaction)
        await interaction.response.defer(ephemeral=response_ephemeral)
        await _send_started_pomodoro(
            interaction,
            mode="break",
            duration=None,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroRestartView(disabled=True),
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
                    voice_channel_select_enabled=interaction.guild is not None,
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
                voice_channel_select_enabled=interaction.guild is not None,
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
                    voice_channel_select_enabled=interaction.guild is not None,
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

        payload = PomodoroEmbeds.timer_stopped_embed(result.message)
        replacement_view = PomodoroStoppedView(interaction.user.id)
        if interaction.message is not None:
            try:
                await interaction.message.edit(**payload, view=replacement_view)
                return
            except discord.HTTPException:
                pass

        await interaction.followup.send(
            ephemeral=response_ephemeral,
            **payload,
            view=replacement_view,
        )


class PomodoroStoppedFocusButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:stopped:focus:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Start Focus",
                style=discord.ButtonStyle.success,
                custom_id=f"pomodoro:stopped:focus:{user_id}",
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
    ) -> "PomodoroStoppedFocusButton":
        del interaction
        return cls(
            int(match.group("user_id")),
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
            duration=None,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroStoppedView(self.user_id, disabled=True),
            response_ephemeral=response_ephemeral,
        )


class PomodoroStoppedBreakButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:stopped:break:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Start Break",
                style=discord.ButtonStyle.primary,
                custom_id=f"pomodoro:stopped:break:{user_id}",
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
    ) -> "PomodoroStoppedBreakButton":
        del interaction
        return cls(
            int(match.group("user_id")),
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
            duration=None,
            target_channel=None,
            use_member_voice=True,
            skip_voice=False,
            source_message=interaction.message,
            source_disabled_view=PomodoroStoppedView(self.user_id, disabled=True),
            response_ephemeral=response_ephemeral,
        )


class PomodoroStoppedCustomTimerButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"pomodoro:stopped:custom:(?P<user_id>\d+)",
):
    def __init__(self, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Custom Timer",
                style=discord.ButtonStyle.secondary,
                custom_id=f"pomodoro:stopped:custom:{user_id}",
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
    ) -> "PomodoroStoppedCustomTimerButton":
        del interaction
        return cls(
            int(match.group("user_id")),
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
