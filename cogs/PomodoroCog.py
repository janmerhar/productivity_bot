# PomodoroCog.py

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
        end_time, resolved_duration, created_job = await asyncio.to_thread(
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

    if interaction.guild is None or target_channel is None:
        voice_error = "Audio off — not in a voice channel."
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
    payload["content"] = voice_error or None

    if interaction.channel is None:
        posted_message = await interaction.followup.send(wait=True, **payload)
    else:
        posted_message = await interaction.channel.send(**payload)
        await interaction.followup.send(
            ephemeral=True,
            content="Pomodoro started.",
        )

    await PomodoroFunctions.bind_timer_message(
        job_id=str(created_job.id),
        channel_id=interaction.channel_id,
        guild_id=interaction.guild_id,
        message_id=posted_message.id,
    )


class PomodoroCog(commands.Cog):
    pomodoro_group = app_commands.Group(name="pomodoro", description="Pomodoro timers")

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("PomodoroCog cog loaded")

    async def _build_active_timer_payload(
        self,
        interaction: discord.Interaction,
        *,
        ephemeral: bool,
        title_override: Optional[str] = None,
        description_override: Optional[str] = None,
    ) -> Optional[dict]:
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
            return None

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

        duration_minutes = PomodoroFunctions._resolve_total_duration_minutes(data)
        duration = str(duration_minutes) if duration_minutes > 0 else "?"

        paused_value = data.get("paused")
        if isinstance(paused_value, str):
            is_paused = paused_value.strip().lower() in ("1", "true", "yes", "on")
        else:
            is_paused = bool(paused_value)

        auto_cycle_enabled = PomodoroFunctions._is_truthy(data.get("auto_cycle"))

        if is_paused:
            remaining_seconds_raw = str(
                data.get("paused_remaining_seconds", "")
            ).strip()
            try:
                remaining_seconds = int(remaining_seconds_raw)
            except ValueError:
                remaining_seconds = 0
            selected_end_time = None
        else:
            remaining_seconds = 0

        user_raw = str(data.get("user", "")).strip()
        owner_id = int(user_raw) if user_raw.isdigit() else interaction.user.id

        join_url: Optional[str] = None
        if interaction.guild is not None:
            session = PomodoroVoiceManager.sessions.get(interaction.guild.id)
            if session is not None:
                channel = interaction.guild.get_channel(session.voice_channel_id)
                if isinstance(channel, discord.VoiceChannel):
                    join_url = channel.jump_url

        resolved_description: Optional[str] = None
        if description_override is not None:
            resolved_description = description_override.format(mode=mode.capitalize())

        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            duration,
            selected_end_time,
            title=title_override,
            description=resolved_description,
        )
        embed = payload.get("embed")
        if is_paused and isinstance(embed, discord.Embed):
            embed.title = f"{mode.capitalize()} Session • Paused"
            embed.description = PomodoroEmbeds.paused_description(
                remaining_seconds=remaining_seconds if remaining_seconds > 0 else None,
                remaining_minutes=duration,
            )
            embed.color = discord.Colour.orange()
            for idx, field in enumerate(embed.fields):
                if (field.name or "").strip().lower() == "ends":
                    embed.set_field_at(
                        idx,
                        name=field.name,
                        value="Paused",
                        inline=field.inline,
                    )

        payload["view"] = PomodoroStartView(
            owner_id,
            join_url=join_url,
            mode=mode,
            end_time=selected_end_time,
            is_paused=is_paused,
            auto_cycle_enabled=auto_cycle_enabled,
            voice_channel_select_enabled=interaction.guild is not None,
        )
        return payload

    @pomodoro_group.command(name="start", description="Start a pomodoro timer")
    @app_commands.describe(
        mode="Pick focus or break",
        duration="Duration in minutes (optional)",
        voice_channel="Voice channel to join (optional)",
        autojoin="Automatically join your current voice channel",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Focus", value="focus"),
            app_commands.Choice(name="Break", value="break"),
        ],
        autojoin=[
            app_commands.Choice(name="On", value="on"),
            app_commands.Choice(name="Off", value="off"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def pomodoro(
        self,
        interaction: discord.Interaction,
        mode: Optional[app_commands.Choice[str]] = None,
        duration: Optional[int] = None,
        voice_channel: Optional[discord.VoiceChannel] = None,
        autojoin: Optional[app_commands.Choice[str]] = None,
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
        autojoin_enabled = autojoin is None or autojoin.value == "on"

        try:
            end_time, resolved_duration, created_job = await asyncio.to_thread(
                PomodoroFunctions.create_timer,
                interaction.guild_id,
                channel_id,
                mode_value,
                duration_value,
                user_id,
            )
        except ValueError as exc:
            error_message = str(exc).strip()
            if (
                "only one pomodoro timer can be active per server"
                in error_message.lower()
            ):
                active_payload = await self._build_active_timer_payload(
                    interaction,
                    ephemeral=ephemeral,
                )
                if active_payload is not None:
                    await interaction.followup.send(
                        ephemeral=ephemeral,
                        content=error_message,
                        **active_payload,
                    )
                    return
            raise ValidationError(
                error_message,
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
        if target_channel is None and autojoin_enabled:
            member = interaction.user
            if isinstance(member, discord.Member) and member.voice:
                target_channel = member.voice.channel

        if interaction.guild is None:
            voice_error = None
        elif target_channel is None:
            voice_error = (
                "Audio off — not in a voice channel." if autojoin_enabled else None
            )
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
        payload["content"] = voice_error or None

        if ephemeral:
            await interaction.followup.send(ephemeral=True, **payload)
            return

        if interaction.channel is None:
            posted_message = await interaction.followup.send(
                ephemeral=False,
                wait=True,
                **payload,
            )
        else:
            posted_message = await interaction.channel.send(**payload)
            await interaction.followup.send(
                ephemeral=True,
                content="Pomodoro started.",
            )

        await PomodoroFunctions.bind_timer_message(
            job_id=str(created_job.id),
            channel_id=interaction.channel_id,
            guild_id=interaction.guild_id,
            message_id=posted_message.id,
        )

    @pomodoro_group.command(name="stop", description="Stop your active pomodoro timer")
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
                "No active pomodoro timers were running.",
                description="No active pomodoro timers were found.",
            )
            payload["view"] = PomodoroStoppedView(interaction.user.id)
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return

        payload = PomodoroEmbeds.timer_stopped_embed(result.message)
        payload["view"] = PomodoroStoppedView(interaction.user.id)
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @pomodoro_group.command(
        name="pause", description="Pause your active pomodoro timer"
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def pomodoro_pause(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)

        result = await PomodoroFunctions.pause_user_pomodoro(interaction)
        if not result.ok:
            no_active_timer = "don't have an active pomodoro" in result.message.lower()
            if no_active_timer:
                payload = PomodoroEmbeds.timer_stopped_embed(
                    "No active pomodoro timers were running.",
                    description="No active pomodoro timers were found.",
                )
                payload["view"] = PomodoroStoppedView(interaction.user.id)
                await interaction.followup.send(ephemeral=ephemeral, **payload)
                return
            await interaction.followup.send(ephemeral=ephemeral, content=result.message)
            return

        mode = result.mode or "focus"
        duration_minutes = result.duration_minutes or result.remaining_minutes or 1
        remaining_minutes = (
            result.remaining_minutes if result.remaining_minutes else "?"
        )

        join_url: Optional[str] = None
        if interaction.guild is not None:
            session = PomodoroVoiceManager.sessions.get(interaction.guild.id)
            if session is not None:
                channel = interaction.guild.get_channel(session.voice_channel_id)
                if isinstance(channel, discord.VoiceChannel):
                    join_url = channel.jump_url

        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            duration_minutes,
            None,
        )
        embed = payload.get("embed")
        if isinstance(embed, discord.Embed):
            embed.title = f"{mode.capitalize()} Session • Paused"
            embed.description = PomodoroEmbeds.paused_description(
                remaining_seconds=result.remaining_seconds,
                remaining_minutes=remaining_minutes,
            )
            embed.color = discord.Colour.orange()
            for idx, field in enumerate(embed.fields):
                if (field.name or "").strip().lower() == "ends":
                    embed.set_field_at(
                        idx,
                        name=field.name,
                        value="Paused",
                        inline=field.inline,
                    )

        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url,
            mode=mode,
            end_time=None,
            is_paused=True,
            voice_channel_select_enabled=interaction.guild is not None,
        )
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @pomodoro_group.command(
        name="resume", description="Resume your paused pomodoro timer"
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def pomodoro_resume(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)

        result = await PomodoroFunctions.resume_user_pomodoro(interaction)
        if not result.ok:
            no_active_timer = "don't have an active pomodoro" in result.message.lower()
            if no_active_timer:
                payload = PomodoroEmbeds.timer_stopped_embed(
                    "No active pomodoro timers were running.",
                    description="No active pomodoro timers were found.",
                )
                payload["view"] = PomodoroStoppedView(interaction.user.id)
                await interaction.followup.send(ephemeral=ephemeral, **payload)
                return
            already_running = "already running" in result.message.lower()
            if already_running:
                active_payload = await self._build_active_timer_payload(
                    interaction,
                    ephemeral=ephemeral,
                    description_override="{mode} timer is already running.",
                )
                if active_payload is not None:
                    await interaction.followup.send(
                        ephemeral=ephemeral, **active_payload
                    )
                    return
            await interaction.followup.send(ephemeral=ephemeral, content=result.message)
            return

        if result.end_time is None or result.duration_minutes is None:
            await interaction.followup.send(ephemeral=ephemeral, content=result.message)
            return

        mode = result.mode or "focus"
        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            result.duration_minutes,
            result.end_time,
        )
        embed = payload.get("embed")
        if isinstance(embed, discord.Embed):
            embed.title = f"{mode.capitalize()} Session"
            embed.description = PomodoroEmbeds.running_description(result.end_time)

        join_url: Optional[str] = None
        if interaction.guild is not None:
            session = PomodoroVoiceManager.sessions.get(interaction.guild.id)
            if session is not None:
                channel = interaction.guild.get_channel(session.voice_channel_id)
                if isinstance(channel, discord.VoiceChannel):
                    join_url = channel.jump_url

        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url,
            mode=mode,
            end_time=result.end_time,
            voice_channel_select_enabled=interaction.guild is not None,
        )
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @pomodoro_group.command(
        name="extend",
        description="Extend your active pomodoro timer",
    )
    @app_commands.describe(
        minutes="How many minutes to add",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def pomodoro_extend(
        self,
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 1, 240] = 5,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)

        result = await PomodoroFunctions.extend_user_pomodoro(
            interaction,
            minutes=minutes,
        )
        if not result.ok:
            no_active_timer = "don't have an active pomodoro" in result.message.lower()
            if no_active_timer:
                payload = PomodoroEmbeds.timer_stopped_embed(
                    "No active pomodoro timers were running.",
                    description="No active pomodoro timers were found.",
                )
                payload["view"] = PomodoroStoppedView(interaction.user.id)
                await interaction.followup.send(ephemeral=ephemeral, **payload)
                return
            await interaction.followup.send(ephemeral=ephemeral, content=result.message)
            return

        if result.end_time is None or result.duration_minutes is None:
            await interaction.followup.send(ephemeral=ephemeral, content=result.message)
            return

        mode = result.mode or "focus"
        payload = PomodoroEmbeds.insert_timer_embed(
            mode,
            result.duration_minutes,
            result.end_time,
        )
        embed = payload.get("embed")
        if isinstance(embed, discord.Embed):
            embed.title = "Pomodoro Extended"
            embed.description = (
                f"{mode.capitalize()} timer extended by {minutes} minute(s)."
            )

        join_url: Optional[str] = None
        if interaction.guild is not None:
            session = PomodoroVoiceManager.sessions.get(interaction.guild.id)
            if session is not None:
                channel = interaction.guild.get_channel(session.voice_channel_id)
                if isinstance(channel, discord.VoiceChannel):
                    join_url = channel.jump_url

        payload["view"] = PomodoroStartView(
            interaction.user.id,
            join_url=join_url,
            mode=mode,
            end_time=result.end_time,
            voice_channel_select_enabled=interaction.guild is not None,
        )
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @pomodoro_group.command(
        name="active",
        description="Show the active pomodoro session",
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def pomodoro_active(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(ephemeral=ephemeral)
        payload = await self._build_active_timer_payload(
            interaction,
            ephemeral=ephemeral,
        )
        if payload is None:
            payload = PomodoroEmbeds.timer_stopped_embed(
                "No active pomodoro timers were running.",
                description="No active pomodoro timers were found.",
            )
            payload["view"] = PomodoroStoppedView(interaction.user.id)
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return
        await interaction.followup.send(ephemeral=ephemeral, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(PomodoroCog(client))
    client.tree.add_command(start_pomodoro_context_menu)
