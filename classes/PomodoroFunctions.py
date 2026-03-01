import asyncio
import datetime
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from embeds.PomodoroEmbeds import PomodoroEmbeds
from classes.DailyJob import DailyJob, OneTimeSchedule2
from classes.DailyJobManager import DailyJobManager
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from config.db import mongo_db
import discord


@dataclass
class PomodoroStopResult:
    ok: bool
    message: str


@dataclass
class PomodoroExtendResult:
    ok: bool
    message: str
    end_time: Optional[datetime.datetime] = None
    duration_minutes: Optional[int] = None


class PomodoroFunctions:
    @staticmethod
    def create_timer(
        guild_id: Optional[int],
        channel_id: int,
        mode: str,
        duration_minutes: Optional[int],
        user_id: Union[int, str],
    ) -> Tuple[datetime.datetime, int]:
        end_time, resolved_duration, data, schedule = (
            PomodoroFunctions.insert_pomodoro_timer(
                channel_id=channel_id,
                mode=mode,
                duration_minutes=duration_minutes,
                user_id=user_id,
            )
        )
        manager = DailyJobManager()
        if guild_id is not None:
            active_jobs = manager.list_jobs(channel_id=None, guild_id=guild_id)
            if any(job.type == "pomodoro" for job in active_jobs):
                raise ValueError(
                    "Only one pomodoro timer can be active per server. "
                    "Stop the current timer first."
                )
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
            resolved_duration = 30 if normalized_mode == "focus" else 5

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

    @staticmethod
    async def extend_user_pomodoro(
        interaction: discord.Interaction,
        *,
        minutes: int = 5,
        expected_end_time: Optional[datetime.datetime] = None,
    ) -> PomodoroExtendResult:
        if minutes <= 0:
            return PomodoroExtendResult(
                ok=False,
                message="Extension minutes must be greater than zero.",
            )

        manager = DailyJobManager()
        guild_id = interaction.guild_id
        channel_id = interaction.channel_id
        user_id = str(interaction.user.id)

        try:
            jobs = await asyncio.to_thread(
                manager.list_jobs,
                channel_id,
                guild_id,
            )
        except Exception:
            return PomodoroExtendResult(
                ok=False,
                message="Something went wrong while fetching pomodoros.",
            )

        user_jobs = [
            job
            for job in jobs
            if job.type == "pomodoro" and str(job.data.get("user")) == user_id
        ]
        if not user_jobs:
            return PomodoroExtendResult(
                ok=False,
                message="You don't have an active pomodoro in this channel.",
            )

        def _normalized(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
            if dt is None:
                return None
            if dt.tzinfo is not None and dt.utcoffset() is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.replace(second=0, microsecond=0)

        normalized_expected = _normalized(expected_end_time)
        selected_job = None
        selected_job_end_time = None
        best_distance_seconds: Optional[float] = None

        for job in user_jobs:
            scheduled = PomodoroFunctions.parse_schedule_datetime(job.schedule)
            if scheduled is None:
                continue
            normalized_scheduled = _normalized(scheduled)
            if normalized_scheduled is None:
                continue
            if normalized_expected is None:
                if selected_job_end_time is None or normalized_scheduled > selected_job_end_time:
                    selected_job = job
                    selected_job_end_time = normalized_scheduled
                continue
            if normalized_scheduled == normalized_expected:
                selected_job = job
                selected_job_end_time = normalized_scheduled
                best_distance_seconds = 0.0
                break
            distance_seconds = abs(
                (normalized_scheduled - normalized_expected).total_seconds()
            )
            if (
                best_distance_seconds is None
                or distance_seconds < best_distance_seconds
            ):
                best_distance_seconds = distance_seconds
                selected_job = job
                selected_job_end_time = normalized_scheduled

        if selected_job is None or selected_job_end_time is None:
            return PomodoroExtendResult(
                ok=False,
                message="I couldn't find an active pomodoro to extend.",
            )

        current_duration_raw = str((selected_job.data or {}).get("duration") or "").strip()
        try:
            current_duration = int(current_duration_raw)
        except ValueError:
            current_duration = 0

        new_duration = max(0, current_duration) + minutes
        new_end_time = selected_job_end_time + datetime.timedelta(minutes=minutes)
        new_end_time = new_end_time.replace(second=0, microsecond=0)

        try:
            update_result = await asyncio.to_thread(
                mongo_db["tasks"].update_one,
                {"_id": selected_job.id, "last_run": None},
                {
                    "$set": {
                        "schedule.datetime": new_end_time.isoformat(),
                        "data.duration": str(new_duration),
                    }
                },
            )
        except Exception:
            return PomodoroExtendResult(
                ok=False,
                message="Something went wrong while extending that pomodoro.",
            )

        if update_result.modified_count <= 0:
            return PomodoroExtendResult(
                ok=False,
                message="I couldn't extend that pomodoro. Please try again.",
            )

        await asyncio.to_thread(manager.fetch_jobs)

        if guild_id is not None:
            PomodoroVoiceManager.extend_end_time_for_guild(guild_id, new_end_time)

        return PomodoroExtendResult(
            ok=True,
            message=f"Extended by {minutes} minutes.",
            end_time=new_end_time,
            duration_minutes=new_duration,
        )
