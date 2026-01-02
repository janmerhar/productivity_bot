import asyncio
import datetime
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from embeds.PomodoroEmbeds import PomodoroEmbeds
from classes.DailyJob import DailyJob, OneTimeSchedule2
from classes.DailyJobManager import DailyJobManager
from classes.PomodoroVoiceManager import PomodoroVoiceManager
import discord


@dataclass
class PomodoroStopResult:
    ok: bool
    message: str


class PomodoroFunctions:
    @staticmethod
    def create_timer(
        guild_id: Optional[int],
        channel_id: int,
        mode: str,
        duration_minutes: Optional[int],
        user_id: Union[int, str],
    ) -> Tuple[datetime.datetime, int]:
        from classes.DailyJobManager import DailyJobManager

        end_time, resolved_duration, data, schedule = (
            PomodoroFunctions.insert_pomodoro_timer(
                channel_id=channel_id,
                mode=mode,
                duration_minutes=duration_minutes,
                user_id=user_id,
            )
        )
        manager = DailyJobManager()
        manager.insert_job(guild_id, channel_id, "pomodoro", data, schedule)

        return end_time, resolved_duration

    @staticmethod
    def insert_timer(
        channel_id: int,
        mode: str,
        duration: Optional[int],
        user_id: Union[int, str],
    ) -> Tuple[datetime.datetime, int, Dict[str, str], OneTimeSchedule2]:
        end_time, duration_minutes, data, schedule = (
            PomodoroFunctions.insert_pomodoro_timer(
                channel_id=channel_id,
                mode=mode,
                duration_minutes=duration,
                user_id=user_id,
            )
        )

        return end_time, duration_minutes, data, schedule

    @staticmethod
    def insert_pomodoro_timer(
        channel_id: int,
        mode: str,
        duration_minutes: Optional[int],
        user_id: Union[int, str],
    ) -> Tuple[datetime.datetime, int, Dict[str, str], OneTimeSchedule2]:
        normalized_mode = mode.lower()
        if normalized_mode not in ("focus", "break"):
            raise ValueError("Invalid pomodoro mode.")

        resolved_duration = duration_minutes
        if resolved_duration is None:
            resolved_duration = 50 if normalized_mode == "focus" else 20

        if resolved_duration <= 0:
            raise ValueError("Pomodoro duration must be greater than zero.")

        end_time = (
            datetime.datetime.now() + datetime.timedelta(minutes=resolved_duration)
        ).replace(second=0, microsecond=0)

        schedule = OneTimeSchedule2(datetime=end_time.isoformat())
        data = {
            "mode": normalized_mode,
            "duration": str(resolved_duration),
            "user": str(user_id),
        }

        return end_time, resolved_duration, data, schedule

    @staticmethod
    def parse_schedule_datetime(
        schedule: Optional[Mapping[str, Any]],
    ) -> Optional[datetime.datetime]:
        if not schedule:
            return None
        raw_value = schedule.get("datetime")
        if not raw_value:
            return None
        try:
            return datetime.datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    @staticmethod
    def pomodoro_payload(job: DailyJob) -> Dict[str, Any]:
        data = job.data or {}
        mode = str(data.get("mode", "focus")).lower()
        duration = data.get("duration", "")
        user_id = data.get("user")
        end_time = PomodoroFunctions.parse_schedule_datetime(job.schedule)

        return PomodoroEmbeds.timer_complete_embed(
            mode=mode,
            duration_minutes=duration,
            end_time=end_time,
            user_id=user_id,
        )

    @staticmethod
    async def stop_user_pomodoro(
        interaction: discord.Interaction,
    ) -> PomodoroStopResult:
        manager = DailyJobManager()
        guild_id = interaction.guild_id

        try:
            jobs = await asyncio.to_thread(
                manager.list_jobs,
                interaction.channel_id,
                guild_id,
            )
        except Exception:
            return PomodoroStopResult(
                ok=False,
                message="Something went wrong while fetching pomodoros.",
            )

        user_id = str(interaction.user.id)
        user_jobs = [
            job
            for job in jobs
            if job.type == "pomodoro" and str(job.data.get("user")) == user_id
        ]

        if not user_jobs:
            return PomodoroStopResult(
                ok=False,
                message="You don't have an active pomodoro in this channel.",
            )

        deleted_count = 0
        for job in user_jobs:
            try:
                deleted = await asyncio.to_thread(
                    manager.delete_job,
                    str(job.id),
                    interaction.channel_id,
                    guild_id,
                )
            except Exception:
                continue
            if deleted:
                deleted_count += 1

        if deleted_count == 0:
            return PomodoroStopResult(
                ok=False,
                message="I couldn't stop that pomodoro. Please try again.",
            )

        remaining_jobs = await asyncio.to_thread(
            manager.list_jobs,
            interaction.channel_id,
            guild_id,
        )
        remaining_pomodoros = [job for job in remaining_jobs if job.type == "pomodoro"]

        audio_stopped = False
        if interaction.guild is not None and not remaining_pomodoros:
            await PomodoroVoiceManager.stop_for_guild(
                interaction.guild.id,
                force=True,
            )
            audio_stopped = True

        message = f"Stopped {deleted_count} pomodoro timer(s)."
        if audio_stopped:
            message += " Left the voice channel."
        elif interaction.guild is not None:
            message += " Voice stays connected while other pomodoros run."

        return PomodoroStopResult(ok=True, message=message)
