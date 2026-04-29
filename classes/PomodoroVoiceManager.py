# PomodoroVoiceManager.py
import asyncio
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import discord

from config.env import env

logger = logging.getLogger(__name__)


@dataclass
class PomodoroVoiceSession:
    guild_id: int
    voice_channel_id: int
    end_time: Optional[datetime.datetime]
    voice_client: discord.VoiceClient


class PomodoroVoiceManager:
    sessions: Dict[int, PomodoroVoiceSession] = {}

    @staticmethod
    def _resolve_audio_path(mode: str) -> Optional[Path]:
        normalized_mode = mode.lower().strip()
        key = "POMODORO_AUDIO_PATH"
        default_path = Path("assets/focus.mp3")
        if normalized_mode == "break":
            key = "POMODORO_BREAK_AUDIO_PATH"
            default_path = Path("assets/break.mp3")
        raw_path = (env.get(key) or "").strip()
        path = Path(raw_path) if raw_path else default_path
        if not path.is_absolute():
            path = Path.cwd() / path
        return path

    @staticmethod
    def _resolve_volume() -> Optional[float]:
        raw_volume = (env.get("POMODORO_AUDIO_VOLUME") or "").strip()
        if not raw_volume:
            return None
        try:
            volume = float(raw_volume)
        except ValueError:
            return None
        return max(0.0, min(volume, 2.0))

    @classmethod
    def _build_audio_source(cls, audio_path: Path) -> discord.AudioSource:
        # -re caps ffmpeg to realtime output rate, preventing unbounded pipe
        # accumulation and disk thrashing when the player is stopped.
        before_options = "-re -stream_loop -1"
        source = discord.FFmpegPCMAudio(
            str(audio_path),
            before_options=before_options,
            options="-vn",
        )
        volume = cls._resolve_volume()
        if volume is not None:
            return discord.PCMVolumeTransformer(source, volume=volume)
        return source

    @classmethod
    async def start_session(
        cls,
        guild: discord.Guild,
        voice_channel: discord.VoiceChannel,
        end_time: Optional[datetime.datetime],
        mode: str,
    ) -> Optional[str]:
        normalized_mode = mode.lower().strip()
        audio_path = cls._resolve_audio_path(normalized_mode)
        if audio_path is None:
            return "Pomodoro audio path could not be resolved."
        if not audio_path.exists() or not audio_path.is_file():
            return f"Audio file not found at `{audio_path}`."

        voice_client = guild.voice_client
        try:
            if voice_client is None or not voice_client.is_connected():
                voice_client = await voice_channel.connect()
            elif (
                not isinstance(voice_client.channel, discord.VoiceChannel)
                or voice_client.channel.id != voice_channel.id
            ):
                await voice_client.move_to(voice_channel)
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            logger.exception("Failed to connect to voice channel %s", voice_channel.id)
            return "I couldn't join that voice channel. Check my permissions."

        for _ in range(20):
            current_voice_client = guild.voice_client or voice_client
            if current_voice_client is not None and current_voice_client.is_connected():
                voice_client = current_voice_client
                break
            await asyncio.sleep(0.25)
        else:
            return "I couldn't keep the voice connection alive. Please try again."

        try:
            if voice_client.is_playing() or voice_client.is_paused():
                # Grab the process reference before stop() so we can force-kill
                # it regardless of whether the AudioPlayer cleanup thread runs
                # promptly. Without this, zombied ffmpeg processes accumulate.
                old_source = voice_client.source
                underlying = getattr(old_source, "original", old_source)
                old_proc = getattr(underlying, "_process", None)
                voice_client.stop()
                if old_proc is not None and old_proc.poll() is None:
                    try:
                        old_proc.kill()
                    except Exception:
                        pass

            source = cls._build_audio_source(audio_path)
            voice_client.play(source)
        except Exception:
            logger.exception("Failed to start audio playback for guild %s", guild.id)
            try:
                if voice_client.is_connected():
                    await voice_client.disconnect(force=True)
            except (discord.Forbidden, discord.HTTPException, discord.ClientException):
                logger.exception(
                    "Failed to disconnect voice client after playback error for guild %s",
                    guild.id,
                )
            return "I joined the voice channel, but audio playback could not start."

        existing = cls.sessions.get(guild.id)
        session_end_time = end_time
        if existing and existing.end_time and end_time:
            session_end_time = max(existing.end_time, end_time)
        elif existing and existing.end_time and end_time is None:
            session_end_time = existing.end_time

        cls.sessions[guild.id] = PomodoroVoiceSession(
            guild_id=guild.id,
            voice_channel_id=voice_channel.id,
            end_time=session_end_time,
            voice_client=voice_client,
        )
        return None

    @classmethod
    async def stop_for_guild(
        cls,
        guild_id: int,
        end_time: Optional[datetime.datetime] = None,
        *,
        force: bool = False,
    ) -> None:
        session = cls.sessions.get(guild_id)
        if session is None:
            return

        if not force and end_time and session.end_time and end_time < session.end_time:
            return

        voice_client = session.voice_client
        try:
            if voice_client.is_playing() or voice_client.is_paused():
                old_source = voice_client.source
                underlying = getattr(old_source, "original", old_source)
                old_proc = getattr(underlying, "_process", None)
                voice_client.stop()
                if old_proc is not None and old_proc.poll() is None:
                    try:
                        old_proc.kill()
                    except Exception:
                        pass
            await voice_client.disconnect(force=True)
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            logger.exception("Failed to disconnect voice client for guild %s", guild_id)
        finally:
            cls.sessions.pop(guild_id, None)

    @classmethod
    def extend_end_time_for_guild(
        cls,
        guild_id: int,
        end_time: datetime.datetime,
    ) -> None:
        session = cls.sessions.get(guild_id)
        if session is None:
            return
        if session.end_time is None or end_time > session.end_time:
            session.end_time = end_time

    @classmethod
    def set_end_time_for_guild(
        cls,
        guild_id: int,
        end_time: datetime.datetime,
    ) -> None:
        session = cls.sessions.get(guild_id)
        if session is None:
            return
        session.end_time = end_time

    @classmethod
    def pause_for_guild(cls, guild_id: int) -> bool:
        session = cls.sessions.get(guild_id)
        if session is None:
            return False

        voice_client = session.voice_client
        try:
            if voice_client.is_playing():
                voice_client.pause()
                return True
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            logger.exception("Failed to pause voice client for guild %s", guild_id)
        return False

    @classmethod
    def resume_for_guild(cls, guild_id: int) -> bool:
        session = cls.sessions.get(guild_id)
        if session is None:
            return False

        voice_client = session.voice_client
        try:
            if voice_client.is_paused():
                voice_client.resume()
                return True
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            logger.exception("Failed to resume voice client for guild %s", guild_id)
        return False
