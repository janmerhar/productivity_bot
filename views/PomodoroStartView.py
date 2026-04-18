# PomodoroStartView.py

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
        timeout: float = 120,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
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
                ephemeral=False,
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
            await interaction.response.send_message(ephemeral=False, content=error)
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
    ) -> None:
        super().__init__(title="Select Voice Channel")
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
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

        selected_value = self.voice_select.values[0] if self.voice_select.values else ""
        if selected_value == "__none__":
            from classes.PomodoroVoiceManager import PomodoroVoiceManager

            await PomodoroVoiceManager.stop_for_guild(
                interaction.guild.id,
                force=True,
            )
            await interaction.followup.send(
                ephemeral=False,
                content="Selected voice channel: None (left voice).",
            )
            return

        channel = PomodoroVoiceChannelSelectView._resolve_selected_voice_channel(
            interaction.guild,
            selected_value,
        )
        if channel is None:
            await interaction.followup.send(
                ephemeral=False,
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
            await interaction.followup.send(ephemeral=False, content=error)
            return

        await interaction.followup.send(
            ephemeral=False,
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
        voice_channel_select_enabled: bool = True,
        *,
        timeout: float = 21600,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
        self._is_paused = is_paused
        self._voice_channel_select_enabled = voice_channel_select_enabled

        if not self._voice_channel_select_enabled:
            self.select_voice_channel_button.disabled = True
            self.select_voice_channel_button.label = "Voice (Server only)"
            self.select_voice_channel_button.style = discord.ButtonStyle.secondary

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

    @staticmethod
    def _with_updated_timer_fields(
        embed: Optional[discord.Embed],
        end_time: datetime.datetime,
        duration_minutes: int,
    ) -> Optional[discord.Embed]:
        if embed is None:
            return None
        updated = embed.copy()
        updated.description = PomodoroEmbeds.running_description(end_time)
        updated.set_footer(text=f"{duration_minutes} min")
        for idx, field in enumerate(updated.fields):
            field_name = (field.name or "").strip().lower()
            if field_name == "ends":
                updated.set_field_at(
                    idx,
                    name=field.name,
                    value=PomodoroStartView._relative_timestamp(end_time),
                    inline=field.inline,
                )
            elif field_name == "duration":
                updated.set_field_at(
                    idx,
                    name=field.name,
                    value=f"{duration_minutes} minutes",
                    inline=field.inline,
                )
        return updated

    def _sync_play_pause_button(self) -> None:
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
        duration_minutes: int,
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
        updated.set_footer(text=f"{duration_minutes} min")

        for idx, field in enumerate(updated.fields):
            field_name = (field.name or "").strip().lower()
            if field_name == "ends":
                updated.set_field_at(
                    idx,
                    name=field.name,
                    value="Paused",
                    inline=field.inline,
                )
            elif field_name == "duration":
                updated.set_field_at(
                    idx,
                    name=field.name,
                    value=f"{duration_minutes} minutes",
                    inline=field.inline,
                )
        return updated

    def _with_resumed_timer_fields(
        self,
        embed: Optional[discord.Embed],
        mode: str,
        end_time: datetime.datetime,
        duration_minutes: int,
    ) -> Optional[discord.Embed]:
        updated = self._with_updated_timer_fields(embed, end_time, duration_minutes)
        if updated is None:
            return None

        updated.title = self._mode_title(mode)
        updated.description = PomodoroEmbeds.running_description(end_time)
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

        voice_channel_options = (
            PomodoroVoiceChannelSelectView._build_voice_channel_options(interaction)
        )
        if not voice_channel_options:
            await interaction.response.send_message(
                ephemeral=False,
                content="No available voice channels found.",
            )
            return

        if _POMODORO_MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    PomodoroVoiceChannelSelectModal(
                        user_id=self._user_id,
                        mode=self._mode,
                        end_time=self._end_time,
                        voice_channel_options=voice_channel_options,
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

        from classes.PomodoroFunctions import PomodoroFunctions

        if self._is_paused:
            result = await PomodoroFunctions.resume_user_pomodoro(interaction)
            if (
                not result.ok
                or result.end_time is None
                or result.duration_minutes is None
            ):
                await interaction.response.send_message(
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
                result.duration_minutes,
            )
            if updated_embed is None:
                await interaction.response.send_message(
                    ephemeral=False,
                    content=(
                        "Pomodoro resumed, but I couldn't refresh the timer card. "
                        f"New end: {self._relative_timestamp(result.end_time)}"
                    ),
                )
                return

            await interaction.response.edit_message(embed=updated_embed, view=self)
            return

        result = await PomodoroFunctions.pause_user_pomodoro(interaction)
        if not result.ok:
            await interaction.response.send_message(
                ephemeral=False,
                content=result.message,
            )
            return

        remaining_minutes = result.remaining_minutes or 1
        duration_minutes = result.duration_minutes or remaining_minutes
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
            duration_minutes,
            remaining_minutes,
            result.remaining_seconds,
        )
        if updated_embed is None:
            await interaction.response.send_message(
                ephemeral=False,
                content=f"Paused with {remaining_minutes} minute(s) remaining.",
            )
            return

        await interaction.response.edit_message(embed=updated_embed, view=self)

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

        from classes.PomodoroFunctions import PomodoroFunctions

        result = await PomodoroFunctions.extend_user_pomodoro(
            interaction,
            minutes=5,
            expected_end_time=self._end_time,
        )
        if not result.ok or result.end_time is None or result.duration_minutes is None:
            await interaction.response.send_message(
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
            result.duration_minutes,
        )
        if updated_embed is None:
            await interaction.response.send_message(
                ephemeral=False,
                content=(
                    "Extended by 5 minutes, but I couldn't refresh the timer card. "
                    f"New end: {self._relative_timestamp(result.end_time)}"
                ),
            )
            return

        try:
            await interaction.response.edit_message(embed=updated_embed, view=self)
        except discord.HTTPException:
            fallback_message = (
                "Extended by 5 minutes, but that timer message no longer exists. "
                f"New end: {self._relative_timestamp(result.end_time)}"
            )
            if interaction.response.is_done():
                await interaction.followup.send(
                    ephemeral=False,
                    content=fallback_message,
                )
            else:
                await interaction.response.send_message(
                    ephemeral=False,
                    content=fallback_message,
                )

    @discord.ui.button(label="Voice", style=discord.ButtonStyle.primary)
    async def select_voice_channel_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._handle_select_voice_channel(interaction)

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

        payload = PomodoroEmbeds.timer_stopped_embed(result.message)
        payload["view"] = PomodoroStoppedView(interaction.user.id)
        payload["content"] = None

        try:
            await interaction.message.edit(**payload)
        except discord.HTTPException:
            await interaction.followup.send(ephemeral=False, **payload)
