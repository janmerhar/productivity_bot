import asyncio
import datetime
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
    def __init__(
        self,
        *,
        user_id: int = 0,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
        chain_expires_at: Optional[datetime.datetime] = None,
        timeout: float = 21600,
    ) -> None:
        super().__init__(timeout=timeout)
        self._user_id = user_id
        self._focus_duration = focus_duration
        self._break_duration = break_duration
        self._streak = streak
        self._chain_expires_at = chain_expires_at

    async def _start(
        self, interaction: discord.Interaction, mode: str, duration: Optional[int]
    ) -> None:
        if self._user_id and interaction.user.id != self._user_id:
            await interaction.response.send_message(
                ephemeral=False,
                content="Only the user who completed this pomodoro can do this.",
            )
            return
        await interaction.response.defer(ephemeral=False)

        streak = self._streak
        if self._chain_expires_at is not None and datetime.datetime.now() > self._chain_expires_at:
            streak = 0

        try:
            end_time, resolved_duration, created_job = await asyncio.to_thread(
                PomodoroFunctions.create_timer,
                interaction.guild_id,
                interaction.channel_id,
                mode,
                duration,
                interaction.user.id,
                self._break_duration,
                self._focus_duration,
                streak,
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

        if interaction.guild is None:
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

        job_streak = PomodoroFunctions._safe_int(
            (created_job.data or {}).get("streak"), default=0
        )
        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            resolved_duration,
            end_time,
            focus_duration=self._focus_duration,
            break_duration=self._break_duration,
            streak=job_streak,
        )
        join_url = target_channel.jump_url if target_channel else None
        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url if voice_error is None else None,
            mode=mode,
            end_time=end_time,
            voice_channel_select_enabled=interaction.guild is not None,
            focus_duration=self._focus_duration,
            break_duration=self._break_duration,
            streak=job_streak,
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

    @discord.ui.button(label="Start Focus", style=discord.ButtonStyle.success)
    async def start_focus(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._start(interaction, "focus", self._focus_duration)

    @discord.ui.button(label="Start Break", style=discord.ButtonStyle.primary)
    async def start_break(
        self, interaction: discord.Interaction, _: discord.ui.Button
    ) -> None:
        await self._start(interaction, "break", self._break_duration)
