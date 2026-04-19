import asyncio
from typing import Optional

import discord

from classes.PomodoroFunctions import PomodoroFunctions
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from embeds.PomodoroEmbeds import PomodoroEmbeds
from views.PomodoroStartView import PomodoroStartView
from services.error_reporting import (
    ValidationError,
    UserVisibleError,
    handle_interaction_error,
)


class PomodoroRestartView(discord.ui.View):
    def __init__(self, *, timeout: float = 21600) -> None:
        super().__init__(timeout=timeout)

    async def _start(self, interaction: discord.Interaction, mode: str) -> None:
        await interaction.response.defer(ephemeral=False)

        try:
            end_time, resolved_duration, created_job = await asyncio.to_thread(
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
        target_channel: Optional[discord.VoiceChannel] = None

        if interaction.guild is None or (
            isinstance(interaction.user, discord.Member)
            and interaction.user.voice is None
        ):
            voice_error = "Audio off — not in a voice channel."
        else:
            member = interaction.user
            if isinstance(member, discord.Member) and member.voice:
                target_channel = member.voice.channel

            if target_channel is None:
                voice_error = "Audio off — not in a voice channel."
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
            join_url=join_url if voice_error is None else None,
            mode=mode,
            end_time=end_time,
            voice_channel_select_enabled=interaction.guild is not None,
        )
        payload["content"] = voice_error or None

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
