import asyncio
from typing import Optional

import discord

from classes.PomodoroFunctions import PomodoroFunctions
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from embeds.PomodoroEmbeds import PomodoroEmbeds
from views.PomodoroStartView import PomodoroStartView
from services.error_reporting import ValidationError, UserVisibleError, handle_interaction_error


class PomodoroRestartView(discord.ui.View):
    def __init__(self, *, timeout: float = 21600) -> None:
        super().__init__(timeout=timeout)

    async def _start(
        self, interaction: discord.Interaction, mode: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            end_time, resolved_duration = await asyncio.to_thread(
                PomodoroFunctions.create_timer,
                interaction.guild_id,
                interaction.channel_id,
                mode,
                None,
                interaction.user.id,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    str(exc),
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while starting that pomodoro.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        voice_error: Optional[str] = None
        target_channel: Optional[discord.VoiceChannel] = None

        if interaction.guild is None:
            voice_error = "Voice playback isn't available in DMs."
        else:
            member = interaction.user
            if isinstance(member, discord.Member) and member.voice:
                target_channel = member.voice.channel

            if target_channel is None:
                voice_error = "Join a voice channel so I can play audio."
            else:
                voice_error = await PomodoroVoiceManager.start_session(
                    interaction.guild,
                    target_channel,
                    end_time,
                    mode,
                )

        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            resolved_duration,
            end_time,
        )
        join_url = target_channel.jump_url if target_channel else None
        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url,
            mode=mode,
            end_time=end_time,
        )

        await interaction.followup.send(ephemeral=True, **payload)

        if voice_error:
            await interaction.followup.send(ephemeral=True, content=voice_error)

    @discord.ui.button(label="Start Focus", style=discord.ButtonStyle.success)
    async def start_focus(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._start(interaction, "focus")

    @discord.ui.button(label="Start Relax", style=discord.ButtonStyle.secondary)
    async def start_break(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._start(interaction, "break")
