import datetime
from typing import List, Optional

import discord

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

        member_channel_id = None
        member = interaction.user
        if isinstance(member, discord.Member) and member.voice:
            member_channel = member.voice.channel
            if isinstance(member_channel, discord.VoiceChannel):
                member_channel_id = member_channel.id

        options: List[discord.SelectOption] = []
        for channel in guild.voice_channels:
            permissions = channel.permissions_for(interaction.user)
            if not permissions.view_channel:
                continue
            options.append(
                discord.SelectOption(
                    label=channel.name[:100],
                    value=f"voice:{channel.id}",
                    default=channel.id == member_channel_id,
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
                ephemeral=True,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="Voice playback isn't available in DMs.",
            )
            return

        selected_value = self.voice_select.values[0]
        channel = self._resolve_selected_voice_channel(interaction.guild, selected_value)
        if channel is None:
            await interaction.response.send_message(
                ephemeral=True,
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
            await interaction.response.send_message(ephemeral=True, content=error)
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
                ephemeral=True,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        await interaction.response.defer(ephemeral=True)

        if interaction.guild is None:
            await interaction.followup.send(
                ephemeral=True,
                content="Voice playback isn't available in DMs.",
            )
            return

        selected_value = (
            self.voice_select.values[0] if self.voice_select.values else ""
        )
        channel = PomodoroVoiceChannelSelectView._resolve_selected_voice_channel(
            interaction.guild,
            selected_value,
        )
        if channel is None:
            await interaction.followup.send(
                ephemeral=True,
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
            await interaction.followup.send(ephemeral=True, content=error)
            return

        await interaction.followup.send(
            ephemeral=True,
            content=f"Selected voice channel: {channel.name}",
        )


class PomodoroStartView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        join_url: Optional[str] = None,
        mode: str = "focus",
        end_time: Optional[datetime.datetime] = None,
        *,
        timeout: float = 21600,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._mode = mode
        self._end_time = end_time
        if join_url:
            self.add_item(discord.ui.Button(label="Join Voice", url=join_url))

    @discord.ui.button(label="Select Voice Channel", style=discord.ButtonStyle.primary)
    async def select_voice_channel_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        global _POMODORO_MODAL_SELECTS_SUPPORTED

        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=True,
                content="Only the user who started this pomodoro can do this.",
            )
            return

        if interaction.guild is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="Voice channel selection isn't available in DMs.",
            )
            return

        voice_channel_options = PomodoroVoiceChannelSelectView._build_voice_channel_options(
            interaction
        )
        if not voice_channel_options:
            await interaction.response.send_message(
                ephemeral=True,
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
            ephemeral=True,
            content="Choose a voice channel:",
            view=picker_view,
        )

    @discord.ui.button(label="Stop Pomodoro", style=discord.ButtonStyle.danger)
    async def stop_button(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=True,
                content="Only the user who started this pomodoro can stop it.",
            )
            return

        await interaction.response.defer(ephemeral=True)
        from classes.PomodoroFunctions import PomodoroFunctions

        result = await PomodoroFunctions.stop_user_pomodoro(interaction)
        await interaction.followup.send(ephemeral=True, content=result.message)
