import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.DailyJobManager import DailyJobManager
from classes.PomodoroFunctions import PomodoroFunctions
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from embeds.PomodoroEmbeds import PomodoroEmbeds
from views.PomodoroStartView import PomodoroStartView
from views.PomodoroStoppedView import PomodoroStoppedView
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


@app_commands.context_menu(name="Start Pomodoro")
async def start_pomodoro_context_menu(
    interaction: discord.Interaction,
    _: discord.Message,
) -> None:
    await interaction.response.defer()

    mode_value = "focus"
    duration_value: Optional[int] = None
    user_id = interaction.user.id
    voice_error: Optional[str] = None
    target_channel: Optional[discord.VoiceChannel] = None

    try:
        end_time, resolved_duration = await asyncio.to_thread(
            PomodoroFunctions.create_timer,
            interaction.guild_id,
            interaction.channel_id,
            mode_value,
            duration_value,
            user_id,
        )
    except ValueError as exc:
        raise ValidationError(str(exc), ephemeral=True, cause=exc)
    except Exception as exc:
        raise UserVisibleError(
            "Something went wrong while starting that pomodoro.",
            ephemeral=True,
            cause=exc,
        )

    if interaction.guild is not None:
        member = interaction.user
        if isinstance(member, discord.Member) and member.voice:
            target_channel = member.voice.channel

    if interaction.guild is None:
        voice_error = None
    elif target_channel is None:
        voice_error = "Join a voice channel so I can play audio."
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
        voice_channel_select_enabled=interaction.guild is not None,
    )

    await interaction.followup.send(**payload)

    if voice_error:
        await interaction.followup.send(ephemeral=True, content=voice_error)


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
        ephemeral = resolve_visibility(visibility, default="public")
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
        except ValueError as exc:
            raise ValidationError(
                str(exc),
                ephemeral=ephemeral,
                cause=exc,
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
            voice_error = None
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
            voice_channel_select_enabled=interaction.guild is not None,
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
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        result = await PomodoroFunctions.stop_user_pomodoro(interaction)
        if not result.ok:
            no_active_timer = "don't have an active pomodoro" in result.message.lower()
            if not no_active_timer:
                await interaction.followup.send(
                    ephemeral=ephemeral,
                    content=result.message,
                )
                return

            payload = PomodoroEmbeds.timer_stopped_embed(
                "No active pomodoro timers were running."
            )
            payload["view"] = PomodoroStoppedView(interaction.user.id)
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return

        payload = PomodoroEmbeds.timer_stopped_embed(result.message)
        payload["view"] = PomodoroStoppedView(interaction.user.id)
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @pomodoro_group.command(name="active", description="Show active pomodoro timers")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def pomodoro_active(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)

        manager = DailyJobManager()
        try:
            if interaction.guild_id is None:
                jobs = await asyncio.to_thread(
                    manager.list_jobs,
                    interaction.channel_id,
                    None,
                )
            else:
                jobs = await asyncio.to_thread(
                    manager.list_jobs,
                    None,
                    interaction.guild_id,
                )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while fetching active pomodoros.",
                ephemeral=ephemeral,
                cause=exc,
            )

        pomodoro_jobs = [job for job in jobs if job.type == "pomodoro"]
        if not pomodoro_jobs:
            payload = PomodoroEmbeds.timer_stopped_embed(
                "No active pomodoro timers were running."
            )
            payload["view"] = PomodoroStoppedView(interaction.user.id)
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return

        selected_job = pomodoro_jobs[0]
        selected_end_time = PomodoroFunctions.parse_schedule_datetime(
            selected_job.schedule
        )
        for job in pomodoro_jobs[1:]:
            candidate_end_time = PomodoroFunctions.parse_schedule_datetime(job.schedule)
            if selected_end_time is None and candidate_end_time is not None:
                selected_job = job
                selected_end_time = candidate_end_time
                continue
            if (
                selected_end_time is not None
                and candidate_end_time is not None
                and candidate_end_time < selected_end_time
            ):
                selected_job = job
                selected_end_time = candidate_end_time

        data = selected_job.data or {}
        mode = str(data.get("mode", "focus")).strip().lower()
        if mode not in ("focus", "break"):
            mode = "focus"
        duration = str(data.get("duration", "?")).strip() or "?"
        user_raw = str(data.get("user", "")).strip()
        owner_id = int(user_raw) if user_raw.isdigit() else interaction.user.id

        join_url: Optional[str] = None
        if interaction.guild is not None:
            session = PomodoroVoiceManager.sessions.get(interaction.guild.id)
            if session is not None:
                channel = interaction.guild.get_channel(session.voice_channel_id)
                if isinstance(channel, discord.VoiceChannel):
                    join_url = channel.jump_url

        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            duration,
            selected_end_time,
        )
        payload["view"] = PomodoroStartView(
            owner_id,
            join_url=join_url,
            mode=mode,
            end_time=selected_end_time,
            voice_channel_select_enabled=interaction.guild is not None,
        )
        await interaction.followup.send(ephemeral=ephemeral, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(PomodoroCog(client))
    client.tree.add_command(start_pomodoro_context_menu)
