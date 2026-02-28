import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.PomodoroFunctions import PomodoroFunctions
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from embeds.PomodoroEmbeds import PomodoroEmbeds
from views.PomodoroStartView import PomodoroStartView
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


class PomodoroCog(commands.Cog):
    pomodoro_group = app_commands.Group(name="pomodoro", description="Pomodoro timers")

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("PomodoroCog cog loaded")

    @pomodoro_group.command(name="start", description="Start a pomodoro timer")
    @app_commands.describe(
        mode="Pick focus or break",
        duration="Duration in minutes (optional)",
        voice_channel="Voice channel to join (optional)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Focus", value="focus"),
            app_commands.Choice(name="Break", value="break"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def pomodoro(
        self,
        interaction: discord.Interaction,
        mode: Optional[app_commands.Choice[str]] = None,
        duration: Optional[int] = None,
        voice_channel: Optional[discord.VoiceChannel] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        if duration is not None and duration <= 0:
            raise ValidationError(
                "Duration must be greater than zero.",
                ephemeral=ephemeral,
            )

        await interaction.response.defer(ephemeral=ephemeral)

        channel_id = interaction.channel_id
        mode_value = mode.value if mode is not None else "focus"
        duration_value = duration
        user_id = interaction.user.id
        voice_error: Optional[str] = None
        target_channel: Optional[discord.VoiceChannel] = None

        try:
            end_time, resolved_duration = await asyncio.to_thread(
                PomodoroFunctions.create_timer,
                interaction.guild_id,
                channel_id,
                mode_value,
                duration_value,
                user_id,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while starting that pomodoro.",
                ephemeral=ephemeral,
                cause=exc,
            )

        target_channel = voice_channel
        if target_channel is None:
            member = interaction.user
            if isinstance(member, discord.Member) and member.voice:
                target_channel = member.voice.channel

        if interaction.guild is None:
            voice_error = "Voice playback isn't available in DMs."
        elif target_channel is None:
            voice_error = "Join a voice channel or pick one so I can play audio."
        else:
            voice_error = await PomodoroVoiceManager.start_session(
                interaction.guild,
                target_channel,
                end_time,
                mode_value,
            )

        payload = PomodoroEmbeds.insert_timer_embed(
            mode_value,
            resolved_duration,
            end_time,
        )

        join_url = target_channel.jump_url if target_channel else None
        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url if voice_error is None else None,
            mode=mode_value,
            end_time=end_time,
        )

        await interaction.followup.send(ephemeral=ephemeral, **payload)

        if voice_error:
            await interaction.followup.send(ephemeral=ephemeral, content=voice_error)

    @pomodoro_group.command(
        name="stop", description="Stop your active pomodoro timer"
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def pomodoro_stop(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        await interaction.response.defer(ephemeral=ephemeral)
        result = await PomodoroFunctions.stop_user_pomodoro(interaction)
        await interaction.followup.send(ephemeral=ephemeral, content=result.message)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(PomodoroCog(client))
