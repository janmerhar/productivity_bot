# PomodoroStartView.py

import asyncio
import datetime
from typing import List, Optional

import discord
from embeds.PomodoroEmbeds import PomodoroEmbeds

_POMODORO_MODAL_SELECTS_SUPPORTED = True


class PomodoroVoiceChannelSelectView(discord.ui.View):
    def __init__(
        self,
        *,
        interaction: discord.Interaction,
        user_id: int,
        mode: str,
        end_time: Optional[datetime.datetime],
        source_message: Optional[discord.Message],
        timeout: float = 120,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
        self._source_message = source_message
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
                ephemeral=False,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                ephemeral=False,
                content="Voice playback isn't available in DMs.",
            )
            return

        selected_value = self.voice_select.values[0]

        resolved_channel: Optional[discord.VoiceChannel] = None
        if selected_value != "__none__":
            resolved_channel = self._resolve_selected_voice_channel(
                interaction.guild, selected_value
            )
            if resolved_channel is None:
                await interaction.response.send_message(
                    ephemeral=False,
                    content="That voice channel was not found.",
                )
                return

        await interaction.response.defer()

        from classes.PomodoroVoiceManager import PomodoroVoiceManager

        if resolved_channel is None:
            await PomodoroVoiceManager.stop_for_guild(
                interaction.guild.id,
                force=True,
            )
            status_message = "Selected voice channel: None (left voice)."
            if self._source_message is not None:
                try:
                    await self._source_message.edit(content=status_message)
                except discord.HTTPException:
                    pass
            try:
                await interaction.message.edit(content="Voice channel updated.", view=None)
            except discord.HTTPException:
                await interaction.followup.send(
                    ephemeral=False, content="Voice channel updated."
                )
            return

        error = await PomodoroVoiceManager.start_session(
            interaction.guild,
            resolved_channel,
            self._end_time,
            self._mode,
        )
        if error:
            await interaction.followup.send(ephemeral=False, content=error)
            return

        status_message = f"Selected voice channel: {resolved_channel.name}"
        if self._source_message is not None:
            try:
                await self._source_message.edit(content=status_message)
            except discord.HTTPException:
                pass

        try:
            await interaction.message.edit(content="Voice channel updated.", view=None)
        except discord.HTTPException:
            await interaction.followup.send(
                ephemeral=False, content="Voice channel updated."
            )


class PomodoroVoiceChannelSelectModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        user_id: int,
        mode: str,
        end_time: Optional[datetime.datetime],
        interaction: discord.Interaction,
        source_message: Optional[discord.Message],
    ) -> None:
        super().__init__(title="Select Voice Channel")
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
        self._source_message = source_message

        default_values: List[discord.SelectDefaultValue] = []
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
            text="Voice channel",
            component=self.voice_select,
        )
        self.add_item(self.voice_select_label)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=False,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        await interaction.response.defer(ephemeral=False)

        if interaction.guild is None:
            await interaction.followup.send(
                ephemeral=False,
                content="Voice playback isn't available in DMs.",
            )
            return

        from classes.PomodoroVoiceManager import PomodoroVoiceManager

        if not self.voice_select.values:
            await PomodoroVoiceManager.stop_for_guild(
                interaction.guild.id,
                force=True,
            )

            status_message = "Selected voice channel: None (left voice)."
            if self._source_message is not None:
                try:
                    await self._source_message.edit(content=status_message)
                    return
                except discord.HTTPException:
                    pass

            await interaction.followup.send(
                ephemeral=False,
                content=status_message,
            )
            return

        selected = self.voice_select.values[0]
        channel = interaction.guild.get_channel(selected.id)
        if not isinstance(channel, discord.VoiceChannel):
            await interaction.followup.send(
                ephemeral=False,
                content="That voice channel was not found.",
            )
            return

        error = await PomodoroVoiceManager.start_session(
            interaction.guild,
            channel,
            self._end_time,
            self._mode,
        )
        if error:
            await interaction.followup.send(ephemeral=False, content=error)
            return

        status_message = f"Selected voice channel: {channel.name}"
        if self._source_message is not None:
            try:
                await self._source_message.edit(content=status_message)
                return
            except discord.HTTPException:
                pass

        await interaction.followup.send(
            ephemeral=False,
            content=status_message,
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
        timeout: float = 21600,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
        self._is_paused = is_paused
        self._auto_cycle_enabled = auto_cycle_enabled
        self._voice_channel_select_enabled = voice_channel_select_enabled
        self._focus_duration = focus_duration
        self._break_duration = break_duration
        self._streak = streak

        if not self._voice_channel_select_enabled:
            self.select_voice_channel_button.disabled = True
            self.select_voice_channel_button.label = "Voice (Server only)"
            self.select_voice_channel_button.style = discord.ButtonStyle.secondary
        else:
            self.select_voice_channel_button.label = (
                "Move Voice" if join_url else "Enable Voice"
            )

        self._sync_play_pause_button()

        if join_url:
            self.add_item(discord.ui.Button(label="Join Voice", url=join_url))

    @staticmethod
    def _relative_timestamp(end_time: datetime.datetime) -> str:
        return f"<t:{int(end_time.timestamp())}:R>"

    @staticmethod
    def _mode_title(mode: str) -> str:
        return f"{mode.capitalize()} Session"

    @classmethod
    def _paused_title(cls, mode: str) -> str:
        return f"{cls._mode_title(mode)} • Paused"

    def _with_updated_timer_fields(
        self,
        embed: Optional[discord.Embed],
        end_time: datetime.datetime,
    ) -> Optional[discord.Embed]:
        if embed is None:
            return None
        updated = embed.copy()
        updated.description = PomodoroEmbeds.running_description(end_time)
        updated.set_footer(
            text=PomodoroEmbeds._duration_footer(
                self._focus_duration, self._break_duration, self._streak
            )
        )
        return updated

    def _sync_play_pause_button(self) -> None:
        if self._auto_cycle_enabled:
            self.auto_cycle_button.label = "Auto On"
            self.auto_cycle_button.style = discord.ButtonStyle.success
        else:
            self.auto_cycle_button.label = "Auto Off"
            self.auto_cycle_button.style = discord.ButtonStyle.secondary

        if self._is_paused:
            self.play_pause_button.label = "Resume"
            self.play_pause_button.emoji = "▶️"
            self.play_pause_button.style = discord.ButtonStyle.success
            self.extend_timer_button.disabled = True
            return

        self.play_pause_button.label = "Pause"
        self.play_pause_button.emoji = "⏸️"
        self.play_pause_button.style = discord.ButtonStyle.secondary
        self.extend_timer_button.disabled = False

    def _with_paused_timer_fields(
        self,
        embed: Optional[discord.Embed],
        mode: str,
        remaining_minutes: int,
        remaining_seconds: Optional[int] = None,
    ) -> Optional[discord.Embed]:
        if embed is None:
            return None

        updated = embed.copy()
        updated.title = self._paused_title(mode)
        updated.description = PomodoroEmbeds.paused_description(
            remaining_seconds=remaining_seconds,
            remaining_minutes=remaining_minutes,
        )
        updated.color = discord.Colour.orange()
        updated.set_footer(
            text=PomodoroEmbeds._duration_footer(
                self._focus_duration, self._break_duration, self._streak
            )
        )
        return updated

    def _with_resumed_timer_fields(
        self,
        embed: Optional[discord.Embed],
        mode: str,
        end_time: datetime.datetime,
    ) -> Optional[discord.Embed]:
        updated = self._with_updated_timer_fields(embed, end_time)
        if updated is None:
            return None

        updated.title = self._mode_title(mode)
        updated.color = discord.Colour.green()
        return updated

    async def _handle_select_voice_channel(
        self, interaction: discord.Interaction
    ) -> None:
        global _POMODORO_MODAL_SELECTS_SUPPORTED

        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=False,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                ephemeral=False,
                content="Voice channel selection isn't available in DMs.",
            )
            return

        if _POMODORO_MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    PomodoroVoiceChannelSelectModal(
                        user_id=self._user_id,
                        mode=self._mode,
                        end_time=self._end_time,
                        interaction=interaction,
                        source_message=interaction.message,
                    )
                )
                return
            except discord.HTTPException as exc:
                if exc.code == 50035 and "must be one of (4,)" in str(exc):
                    _POMODORO_MODAL_SELECTS_SUPPORTED = False
                else:
                    raise

        picker_view = PomodoroVoiceChannelSelectView(
            interaction=interaction,
            user_id=self._user_id,
            mode=self._mode,
            end_time=self._end_time,
            source_message=interaction.message,
        )
        await interaction.response.send_message(
            ephemeral=False,
            content="Choose a voice channel:",
            view=picker_view,
        )

    @discord.ui.button(
        label="Pause",
        style=discord.ButtonStyle.secondary,
        emoji="⏸️",
    )
    async def play_pause_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=False,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        await interaction.response.defer()

        from classes.PomodoroFunctions import PomodoroFunctions

        if self._is_paused:
            result = await PomodoroFunctions.resume_user_pomodoro(interaction)
            if (
                not result.ok
                or result.end_time is None
                or result.duration_minutes is None
            ):
                await interaction.followup.send(
                    ephemeral=False,
                    content=result.message,
                )
                return

            self._is_paused = False
            self._end_time = result.end_time
            if result.mode:
                self._mode = result.mode
            self._sync_play_pause_button()

            updated_embed = self._with_resumed_timer_fields(
                (
                    interaction.message.embeds[0]
                    if interaction.message and interaction.message.embeds
                    else None
                ),
                self._mode,
                result.end_time,
            )
            if updated_embed is None:
                await interaction.followup.send(
                    ephemeral=False,
                    content=(
                        "Pomodoro resumed, but I couldn't refresh the timer card. "
                        f"New end: {self._relative_timestamp(result.end_time)}"
                    ),
                )
                return

            try:
                await interaction.message.edit(embed=updated_embed, view=self)
            except discord.HTTPException:
                await interaction.followup.send(
                    ephemeral=False,
                    content=(
                        "Pomodoro resumed, but I couldn't refresh the timer card. "
                        f"New end: {self._relative_timestamp(result.end_time)}"
                    ),
                )
            return

        result = await PomodoroFunctions.pause_user_pomodoro(interaction)
        if not result.ok:
            await interaction.followup.send(
                ephemeral=False,
                content=result.message,
            )
            return

        remaining_minutes = result.remaining_minutes or 1
        if result.mode:
            self._mode = result.mode
        self._end_time = None
        self._is_paused = True
        self._sync_play_pause_button()

        updated_embed = self._with_paused_timer_fields(
            (
                interaction.message.embeds[0]
                if interaction.message and interaction.message.embeds
                else None
            ),
            self._mode,
            remaining_minutes,
            result.remaining_seconds,
        )
        if updated_embed is None:
            await interaction.followup.send(
                ephemeral=False,
                content=f"Paused with {remaining_minutes} minute(s) remaining.",
            )
            return

        try:
            await interaction.message.edit(embed=updated_embed, view=self)
        except discord.HTTPException:
            await interaction.followup.send(
                ephemeral=False,
                content=f"Paused with {remaining_minutes} minute(s) remaining.",
            )

    @discord.ui.button(label="+5 min", style=discord.ButtonStyle.secondary)
    async def extend_timer_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=False,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        if self._is_paused:
            await interaction.response.send_message(
                ephemeral=False,
                content="Resume the pomodoro before extending it.",
            )
            return

        await interaction.response.defer()

        from classes.PomodoroFunctions import PomodoroFunctions

        result = await PomodoroFunctions.extend_user_pomodoro(
            interaction,
            minutes=5,
            expected_end_time=self._end_time,
        )
        if not result.ok or result.end_time is None or result.duration_minutes is None:
            await interaction.followup.send(
                ephemeral=False,
                content=result.message,
            )
            return

        self._end_time = result.end_time
        updated_embed = self._with_updated_timer_fields(
            (
                interaction.message.embeds[0]
                if interaction.message and interaction.message.embeds
                else None
            ),
            result.end_time,
        )
        if updated_embed is None:
            await interaction.followup.send(
                ephemeral=False,
                content=(
                    "Extended by 5 minutes, but I couldn't refresh the timer card. "
                    f"New end: {self._relative_timestamp(result.end_time)}"
                ),
            )
            return

        try:
            await interaction.message.edit(embed=updated_embed, view=self)
        except discord.HTTPException:
            await interaction.followup.send(
                ephemeral=False,
                content=(
                    "Extended by 5 minutes, but that timer message no longer exists. "
                    f"New end: {self._relative_timestamp(result.end_time)}"
                ),
            )

    @discord.ui.button(label="Voice", style=discord.ButtonStyle.primary)
    async def select_voice_channel_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._handle_select_voice_channel(interaction)

    @discord.ui.button(
        label="Auto Off",
        style=discord.ButtonStyle.secondary,
        emoji="🔄",
    )
    async def auto_cycle_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=False,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        await interaction.response.defer()

        from classes.PomodoroFunctions import PomodoroFunctions

        ok, enabled, message = await PomodoroFunctions.toggle_auto_cycle(
            interaction,
            expected_end_time=self._end_time,
            is_paused=self._is_paused,
        )
        if not ok or enabled is None:
            await interaction.followup.send(
                ephemeral=False,
                content=message,
            )
            return

        self._auto_cycle_enabled = enabled
        self._sync_play_pause_button()
        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            await interaction.followup.send(
                ephemeral=False,
                content=f"Auto-cycle {'enabled' if enabled else 'disabled'}.",
            )

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def stop_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=False,
                content="Only the user who started this pomodoro can stop it.",
            )
            return

        await interaction.response.defer(ephemeral=False)
        from classes.PomodoroFunctions import PomodoroFunctions
        from embeds.PomodoroEmbeds import PomodoroEmbeds
        from views.PomodoroStoppedView import PomodoroStoppedView

        result = await PomodoroFunctions.stop_user_pomodoro(interaction)
        if not result.ok:
            await interaction.followup.send(ephemeral=False, content=result.message)
            return

        best_streak = await asyncio.to_thread(
            PomodoroFunctions.fetch_best_pomodoro_streak,
            interaction.user.id,
        )
        payload = PomodoroEmbeds.timer_stopped_embed(
            streak=result.streak,
            best_streak=best_streak,
            focus_duration=self._focus_duration,
            break_duration=self._break_duration,
        )
        payload["view"] = PomodoroStoppedView(
            interaction.user.id,
            focus_duration=self._focus_duration,
            break_duration=self._break_duration,
        )
        payload["content"] = None

        try:
            await interaction.message.edit(**payload)
        except discord.HTTPException:
            await interaction.followup.send(ephemeral=False, **payload)
