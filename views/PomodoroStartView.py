import datetime
from typing import List, Optional

import discord

from services.visibility import inherit_ephemeral_from_interaction
from views.pomodoro_dynamic_items import (
    PomodoroStartAutoCycleButton,
    PomodoroStartExtendButton,
    PomodoroStartPlayPauseButton,
    PomodoroStartSelectVoiceButton,
    PomodoroStartStopButton,
)

_POMODORO_MODAL_SELECTS_SUPPORTED = True


class PomodoroVoiceChannelSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        interaction: discord.Interaction,
        user_id: int,
        mode: str,
        end_time: Optional[datetime.datetime],
        response_ephemeral: bool,
        timeout: float = 120,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
        self._response_ephemeral = bool(response_ephemeral)
        self.voice_select: Optional[discord.ui.Select] = None

        options = self._build_voice_channel_options(interaction)
        if options:
            select = discord.ui.Select(
                placeholder="Voice channel",
                min_values=1,
                max_values=1,
                options=options[:25],
                row=0,
            )
            select.callback = self._on_select_voice_channel
            self.voice_select = select
            self.add_item(select)

    @property
    def has_options(self) -> bool:
        return self.voice_select is not None

    @staticmethod
    def _build_voice_channel_options(
        interaction: discord.Interaction,
    ) -> List[discord.SelectOption]:
        guild = interaction.guild
        if guild is None:
            return []

        default_channel_id = None
        voice_client = guild.voice_client
        if (
            voice_client is not None
            and voice_client.is_connected()
            and isinstance(voice_client.channel, discord.VoiceChannel)
        ):
            default_channel_id = voice_client.channel.id

        member = interaction.user
        if isinstance(member, discord.Member) and member.voice:
            member_channel = member.voice.channel
            if (
                isinstance(member_channel, discord.VoiceChannel)
                and default_channel_id is None
            ):
                default_channel_id = member_channel.id

        options: List[discord.SelectOption] = []
        options.append(
            discord.SelectOption(
                label="None",
                value="__none__",
                default=default_channel_id is None,
            )
        )
        for channel in guild.voice_channels:
            permissions = channel.permissions_for(interaction.user)
            if not permissions.view_channel:
                continue
            options.append(
                discord.SelectOption(
                    label=channel.name[:100],
                    value=f"voice:{channel.id}",
                    default=channel.id == default_channel_id,
                )
            )
            if len(options) >= 25:
                break
        return options

    @staticmethod
    def _resolve_selected_voice_channel(
        guild: discord.Guild,
        selected_value: str,
    ) -> Optional[discord.VoiceChannel]:
        if not selected_value.startswith("voice:"):
            return None
        channel_id = selected_value.split(":", 1)[1].strip()
        if not channel_id.isdigit():
            return None
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.VoiceChannel):
            return None
        return channel

    async def _on_select_voice_channel(self, interaction: discord.Interaction) -> None:
        if self.voice_select is None or not self.voice_select.values:
            await interaction.response.defer()
            return

        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=self._response_ephemeral,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                ephemeral=self._response_ephemeral,
                content="Voice playback isn't available in DMs.",
            )
            return

        selected_value = self.voice_select.values[0]
        if selected_value == "__none__":
            from classes.PomodoroVoiceManager import PomodoroVoiceManager

            await PomodoroVoiceManager.stop_for_guild(
                interaction.guild.id,
                force=True,
            )
            await interaction.response.edit_message(
                content="Selected voice channel: None (left voice).",
                view=self,
            )
            return

        channel = self._resolve_selected_voice_channel(
            interaction.guild, selected_value
        )
        if channel is None:
            await interaction.response.send_message(
                ephemeral=self._response_ephemeral,
                content="That voice channel was not found.",
            )
            return

        from classes.PomodoroVoiceManager import PomodoroVoiceManager

        error = await PomodoroVoiceManager.start_session(
            interaction.guild,
            channel,
            self._end_time,
            self._mode,
        )
        if error:
            await interaction.response.send_message(
                ephemeral=self._response_ephemeral,
                content=error,
            )
            return

        await interaction.response.edit_message(
            content=f"Selected voice channel: {channel.name}",
            view=self,
        )


class PomodoroVoiceChannelSelectModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        user_id: int,
        mode: str,
        end_time: Optional[datetime.datetime],
        voice_channel_options: List[discord.SelectOption],
        response_ephemeral: bool,
    ) -> None:
        super().__init__(title="Select Voice Channel")
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
        self._response_ephemeral = bool(response_ephemeral)
        self.voice_select = discord.ui.Select(
            placeholder="Voice channel",
            min_values=1,
            max_values=1,
            options=voice_channel_options[:25],
        )
        self.voice_select_label = discord.ui.Label(
            text="Voice channel",
            component=self.voice_select,
        )
        self.add_item(self.voice_select_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=self._response_ephemeral,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        await interaction.response.defer(ephemeral=self._response_ephemeral)

        if interaction.guild is None:
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                content="Voice playback isn't available in DMs.",
            )
            return

        selected_value = self.voice_select.values[0] if self.voice_select.values else ""
        if selected_value == "__none__":
            from classes.PomodoroVoiceManager import PomodoroVoiceManager

            await PomodoroVoiceManager.stop_for_guild(
                interaction.guild.id,
                force=True,
            )
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                content="Selected voice channel: None (left voice).",
            )
            return

        channel = PomodoroVoiceChannelSelectView._resolve_selected_voice_channel(
            interaction.guild,
            selected_value,
        )
        if channel is None:
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                content="That voice channel was not found.",
            )
            return

        from classes.PomodoroVoiceManager import PomodoroVoiceManager

        error = await PomodoroVoiceManager.start_session(
            interaction.guild,
            channel,
            self._end_time,
            self._mode,
        )
        if error:
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                content=error,
            )
            return

        await interaction.followup.send(
            ephemeral=self._response_ephemeral,
            content=f"Selected voice channel: {channel.name}",
        )


class PomodoroStartView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        join_url: Optional[str] = None,
        mode: str = "focus",
        end_time: Optional[datetime.datetime] = None,
        is_paused: bool = False,
        auto_cycle_enabled: bool = False,
        voice_channel_select_enabled: bool = True,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
        *,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.add_item(
            PomodoroStartSelectVoiceButton(
                user_id,
                disabled=not voice_channel_select_enabled,
                server_only=not voice_channel_select_enabled,
            )
        )
        self.add_item(PomodoroStartPlayPauseButton(user_id, paused=is_paused))
        self.add_item(PomodoroStartExtendButton(user_id, disabled=is_paused))
        self.add_item(PomodoroStartAutoCycleButton(user_id, enabled=auto_cycle_enabled))
        self.add_item(PomodoroStartStopButton(user_id))

        if join_url:
            self.add_item(discord.ui.Button(label="Join Voice", url=join_url))

    @staticmethod
    def _relative_timestamp(end_time: datetime.datetime) -> str:
        return f"<t:{int(end_time.timestamp())}:R>"

    @staticmethod
    def _with_updated_timer_fields(
        embed: Optional[discord.Embed],
        end_time: datetime.datetime,
        duration_minutes: int,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
    ) -> Optional[discord.Embed]:
        if embed is None:
            return None
        updated = embed.copy()
        from embeds.PomodoroEmbeds import PomodoroEmbeds

        updated.description = PomodoroEmbeds.running_description(end_time)
        updated.set_footer(
            text=PomodoroEmbeds._duration_footer(
                focus_duration, break_duration, streak
            )
        )
        return updated

    @staticmethod
    def _with_paused_timer_fields(
        embed: Optional[discord.Embed],
        mode: str,
        remaining_minutes: int,
        remaining_seconds: Optional[int] = None,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
    ) -> Optional[discord.Embed]:
        if embed is None:
            return None

        updated = embed.copy()
        from embeds.PomodoroEmbeds import PomodoroEmbeds

        updated.title = f"{mode.capitalize()} Session - Paused"
        updated.description = PomodoroEmbeds.paused_description(
            remaining_seconds=remaining_seconds,
            remaining_minutes=remaining_minutes,
        )
        updated.color = discord.Colour.orange()
        updated.set_footer(
            text=PomodoroEmbeds._duration_footer(
                focus_duration, break_duration, streak
            )
        )
        return updated

    @staticmethod
    def _with_resumed_timer_fields(
        embed: Optional[discord.Embed],
        mode: str,
        end_time: datetime.datetime,
        duration_minutes: int,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
    ) -> Optional[discord.Embed]:
        updated = PomodoroStartView._with_updated_timer_fields(
            embed,
            end_time,
            duration_minutes,
            focus_duration,
            break_duration,
            streak,
        )
        if updated is None:
            return None

        updated.title = f"{mode.capitalize()} Session"
        updated.color = discord.Colour.green()
        return updated
