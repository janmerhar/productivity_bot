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
        if normalized_mode == "break":
            key = "POMODORO_BREAK_AUDIO_PATH"
        raw_path = (env.get(key) or "").strip()
        if not raw_path:
            return None
        path = Path(raw_path)
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
        before_options = "-stream_loop -1"
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
            if normalized_mode == "break":
                return (
                    "POMODORO_BREAK_AUDIO_PATH is not set, so I couldn't start break "
                    "audio."
                )
            return "POMODORO_AUDIO_PATH is not set, so I couldn't start focus audio."
        if not audio_path.exists() or not audio_path.is_file():
            return f"Audio file not found at `{audio_path}`."

        voice_client = guild.voice_client
        try:
            if voice_client is None or not voice_client.is_connected():
                voice_client = await voice_channel.connect()
            elif voice_client.channel.id != voice_channel.id:
                await voice_client.move_to(voice_channel)
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            logger.exception("Failed to connect to voice channel %s", voice_channel.id)
            return "I couldn't join that voice channel. Check my permissions."

        if voice_client.is_playing() or voice_client.is_paused():
            voice_client.stop()

        source = cls._build_audio_source(audio_path)
        voice_client.play(source)

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
                voice_client.stop()
            if voice_client.is_connected():
                await voice_client.disconnect(force=True)
        except (discord.Forbidden, discord.HTTPException, discord.ClientException):
            logger.exception("Failed to disconnect voice client for guild %s", guild_id)
        finally:
            cls.sessions.pop(guild_id, None)
