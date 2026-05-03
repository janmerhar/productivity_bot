# PomodoroFunctions.py

import asyncio
import datetime
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple, Union

from embeds.PomodoroEmbeds import PomodoroEmbeds
from classes.DailyJob import DailyJob, OneTimeSchedule2, ScheduleConfig
from classes.DailyJobManager import DailyJobManager
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from config.db import mongo_db
import discord


@dataclass
class PomodoroStopResult:
    ok: bool
    message: str
    streak: int = 0
    focus_duration: Optional[int] = None
    break_duration: Optional[int] = None


@dataclass
class PomodoroExtendResult:
    ok: bool
    message: str
    end_time: Optional[datetime.datetime] = None
    duration_minutes: Optional[int] = None
    mode: Optional[str] = None


@dataclass
class PomodoroPauseResult:
    ok: bool
    message: str
    mode: Optional[str] = None
    duration_minutes: Optional[int] = None
    remaining_minutes: Optional[int] = None
    remaining_seconds: Optional[int] = None


@dataclass
class PomodoroResumeResult:
    ok: bool
    message: str
    mode: Optional[str] = None
    end_time: Optional[datetime.datetime] = None
    duration_minutes: Optional[int] = None


class PomodoroFunctions:
    @staticmethod
    def _normalize_datetime(
        value: Optional[datetime.datetime],
    ) -> Optional[datetime.datetime]:
        if value is None:
            return None
        if value.tzinfo is not None and value.utcoffset() is not None:
            value = value.astimezone().replace(tzinfo=None)
        return value.replace(microsecond=0)

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return False

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _resolve_total_duration_minutes(
        data: Optional[Mapping[str, Any]],
        *,
        fallback: int = 0,
    ) -> int:
        payload = data or {}
        for key in ("total_duration_minutes", "duration"):
            value = PomodoroFunctions._safe_int(payload.get(key), default=0)
            if value > 0:
                return value
        return max(0, fallback)

    @staticmethod
    async def _list_scope_jobs(
        manager: DailyJobManager,
        interaction: discord.Interaction,
    ) -> List[DailyJob]:
        if interaction.guild_id is None:
            return await asyncio.to_thread(
                manager.list_jobs,
                interaction.channel_id,
                None,
            )

        return await asyncio.to_thread(
            manager.list_jobs,
            None,
            interaction.guild_id,
        )

    @staticmethod
    def _scope_message(interaction: discord.Interaction) -> str:
        if interaction.guild_id is None:
            return "in this channel"
        return "on this server"

    @staticmethod
    def _select_user_job_by_pause_state(
        jobs: List[DailyJob],
        *,
        paused: bool,
    ) -> Tuple[Optional[DailyJob], Optional[datetime.datetime]]:
        selected_job: Optional[DailyJob] = None
        selected_end_time: Optional[datetime.datetime] = None

        for job in jobs:
            data = job.data or {}
            if PomodoroFunctions._is_truthy(data.get("paused")) != paused:
                continue
            end_time = PomodoroFunctions._normalize_datetime(
                PomodoroFunctions.parse_schedule_datetime(job.schedule)
            )
            if end_time is None:
                continue
            if selected_end_time is None or end_time > selected_end_time:
                selected_job = job
                selected_end_time = end_time

        return selected_job, selected_end_time

    @staticmethod
    def _next_streak(mode: str, streak: int) -> int:
        if mode == "focus":
            return streak + 1
        return streak

    @staticmethod
    def create_timer(
        guild_id: Optional[int],
        channel_id: int,
        mode: str,
        duration_minutes: Optional[int],
        user_id: Union[int, str],
        break_duration: Optional[int] = None,
        focus_duration: Optional[int] = None,
        streak: int = 0,
    ) -> Tuple[datetime.datetime, int, DailyJob]:
        end_time, resolved_duration, data, schedule = (
            PomodoroFunctions.insert_pomodoro_timer(
                channel_id=channel_id,
                mode=mode,
                duration_minutes=duration_minutes,
                user_id=user_id,
                break_duration=break_duration,
                focus_duration=focus_duration,
                streak=streak,
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

        created_job = manager.insert_job(
            guild_id,
            channel_id,
            "pomodoro",
            data,
            schedule,
        )

        return end_time, resolved_duration, created_job

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
        break_duration: Optional[int] = None,
        focus_duration: Optional[int] = None,
        streak: int = 0,
    ) -> Tuple[datetime.datetime, int, Dict[str, Any], OneTimeSchedule2]:
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
        ).replace(microsecond=0)

        schedule = OneTimeSchedule2(datetime=end_time.isoformat())
        data: Dict[str, Any] = {
            "mode": normalized_mode,
            "duration": str(resolved_duration),
            "total_duration_minutes": str(resolved_duration),
            "user": str(user_id),
            "auto_cycle": False,
            "streak": streak,
        }
        if focus_duration is not None:
            data["focus_duration"] = str(focus_duration)
        if break_duration is not None:
            data["break_duration"] = str(break_duration)

        return end_time, resolved_duration, data, schedule

    @staticmethod
    def parse_schedule_datetime(
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]],
    ) -> Optional[datetime.datetime]:
        if not schedule:
            return None
        if isinstance(schedule, Mapping):
            raw_value = schedule.get("datetime")
        else:
            raw_value = getattr(schedule, "datetime", None)
        if not raw_value:
            return None
        try:
            return datetime.datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    @staticmethod
    async def bind_timer_message(
        *,
        job_id: str,
        channel_id: Optional[int],
        guild_id: Optional[int],
        message_id: int,
    ) -> None:
        manager = DailyJobManager()

        try:
            job = await asyncio.to_thread(
                manager.get_job,
                job_id,
                channel_id if guild_id is None else None,
                guild_id,
            )
        except Exception:
            return

        if job is None:
            return

        data = dict(job.data or {})
        data["message_id"] = str(message_id)

        try:
            await asyncio.to_thread(
                manager.update_job,
                job_id,
                data,
                None,
                None,
                channel_id if guild_id is None else None,
                guild_id,
            )
        except Exception:
            return

    @staticmethod
    async def toggle_auto_cycle(
        interaction: discord.Interaction,
        *,
        expected_end_time: Optional[datetime.datetime] = None,
        is_paused: Optional[bool] = None,
    ) -> Tuple[bool, Optional[bool], str]:
        manager = DailyJobManager()

        try:
            jobs = await PomodoroFunctions._list_scope_jobs(manager, interaction)
        except Exception:
            return False, None, "Something went wrong while updating auto-cycle."

        user_id = str(interaction.user.id)
        user_jobs = [
            job
            for job in jobs
            if job.type == "pomodoro" and str((job.data or {}).get("user")) == user_id
        ]
        if not user_jobs:
            return (
                False,
                None,
                "You don't have an active pomodoro "
                f"{PomodoroFunctions._scope_message(interaction)}.",
            )

        normalized_expected = PomodoroFunctions._normalize_datetime(expected_end_time)
        selected_job: Optional[DailyJob] = None
        best_distance_seconds: Optional[float] = None

        for job in user_jobs:
            paused = PomodoroFunctions._is_truthy((job.data or {}).get("paused"))
            if is_paused is not None and paused != is_paused:
                continue

            scheduled_end_time = PomodoroFunctions._normalize_datetime(
                PomodoroFunctions.parse_schedule_datetime(job.schedule)
            )

            if normalized_expected is None or scheduled_end_time is None:
                if selected_job is None:
                    selected_job = job
                continue

            distance_seconds = abs(
                (scheduled_end_time - normalized_expected).total_seconds()
            )
            if (
                best_distance_seconds is None
                or distance_seconds < best_distance_seconds
            ):
                best_distance_seconds = distance_seconds
                selected_job = job

        if selected_job is None:
            return False, None, "I couldn't find that pomodoro."

        data = dict(selected_job.data or {})
        enabled = not PomodoroFunctions._is_truthy(data.get("auto_cycle"))
        data["auto_cycle"] = enabled

        try:
            updated = await asyncio.to_thread(
                manager.update_job,
                str(selected_job.id),
                data=data,
                channel_id=(
                    interaction.channel_id if interaction.guild_id is None else None
                ),
                guild_id=interaction.guild_id,
            )
        except Exception:
            return False, None, "Something went wrong while updating auto-cycle."

        if not updated:
            return False, None, "I couldn't update auto-cycle. Please try again."

        return (
            True,
            enabled,
            ("Auto-cycle enabled." if enabled else "Auto-cycle disabled."),
        )

    @staticmethod
    def pomodoro_payload(job: DailyJob, streak: int = 0) -> Dict[str, Any]:
        data = job.data or {}
        mode = str(data.get("mode", "focus")).strip().lower()
        if mode not in ("focus", "break"):
            mode = "focus"

        duration = data.get("duration", "")
        user_id = str(data.get("user", "")).strip()
        end_time = PomodoroFunctions.parse_schedule_datetime(job.schedule)
        raw_focus = str(data.get("focus_duration") or "").strip()
        raw_break = str(data.get("break_duration") or "").strip()

        payload = PomodoroEmbeds.timer_complete_embed(
            mode=mode,
            duration_minutes=duration,
            end_time=end_time,
            user_id=user_id or None,
            focus_duration=int(raw_focus) if raw_focus.isdigit() else None,
            break_duration=int(raw_break) if raw_break.isdigit() else None,
            streak=streak,
        )

        if user_id.isdigit():
            if mode == "break":
                payload["content"] = f"<@{user_id}> Break finished."
            else:
                payload["content"] = f"<@{user_id}> Focus session finished."

        return payload

    @staticmethod
    def update_best_pomodoro_streak(user_id: int, streak: int) -> None:
        mongo_db["user_stats"].update_one(
            {"user_id": str(user_id)},
            {"$max": {"pomodoro.best_streak": streak}},
            upsert=True,
        )

    @staticmethod
    def fetch_best_pomodoro_streak(user_id: int) -> int:
        doc = mongo_db["user_stats"].find_one({"user_id": str(user_id)})
        if doc is None:
            return 0
        return PomodoroFunctions._safe_int(
            (doc.get("pomodoro") or {}).get("best_streak"), default=0
        )

    @staticmethod
    def fetch_pomodoro_streak_info(
        user_id: int,
        guild_id: Optional[int],
        channel_id: int,
    ) -> Tuple[int, int]:
        last = PomodoroFunctions.fetch_last_pomodoro_streak(user_id, guild_id, channel_id)
        best = PomodoroFunctions.fetch_best_pomodoro_streak(user_id)
        return last, best

    @staticmethod
    def fetch_last_pomodoro_streak(
        user_id: int,
        guild_id: Optional[int],
        channel_id: int,
    ) -> int:
        query: Dict[str, Any] = {
            "type": "pomodoro",
            "data.user": str(user_id),
            "last_run": {"$ne": None},
        }
        if guild_id is not None:
            query["guild_id"] = guild_id
        else:
            query["channel_id"] = channel_id

        doc = mongo_db["tasks"].find_one(query, sort=[("last_run", -1)])
        if doc is None:
            return 0
        data = doc.get("data") or {}
        streak = PomodoroFunctions._safe_int(data.get("streak"), default=0)
        mode = str(data.get("mode", "")).strip().lower()
        return PomodoroFunctions._next_streak(mode, streak)

    @staticmethod
    async def stop_user_pomodoro(
        interaction: discord.Interaction,
    ) -> PomodoroStopResult:
        manager = DailyJobManager()

        try:
            jobs = await PomodoroFunctions._list_scope_jobs(manager, interaction)
        except Exception:
            return PomodoroStopResult(
                ok=False,
                message="Something went wrong while fetching pomodoros.",
            )

        user_id = str(interaction.user.id)
        user_jobs = [
            job
            for job in jobs
            if job.type == "pomodoro" and str((job.data or {}).get("user")) == user_id
        ]

        if not user_jobs:
            return PomodoroStopResult(
                ok=False,
                message=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )

        first_job_data = user_jobs[0].data or {}
        last_streak = PomodoroFunctions._safe_int(first_job_data.get("streak"), default=0)
        raw_focus = str(first_job_data.get("focus_duration") or "").strip()
        raw_break = str(first_job_data.get("break_duration") or "").strip()
        stop_focus_duration = int(raw_focus) if raw_focus.isdigit() else None
        stop_break_duration = int(raw_break) if raw_break.isdigit() else None

        deleted_count = 0
        for job in user_jobs:
            try:
                deleted = await asyncio.to_thread(
                    manager.delete_job,
                    str(job.id),
                    (
                        None
                        if interaction.guild_id is not None
                        else interaction.channel_id
                    ),
                    interaction.guild_id,
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

        remaining_jobs = await PomodoroFunctions._list_scope_jobs(manager, interaction)
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

        return PomodoroStopResult(ok=True, message=message, streak=last_streak, focus_duration=stop_focus_duration, break_duration=stop_break_duration)

    @staticmethod
    async def pause_user_pomodoro(
        interaction: discord.Interaction,
    ) -> PomodoroPauseResult:
        manager = DailyJobManager()
        guild_id = interaction.guild_id

        try:
            jobs = await PomodoroFunctions._list_scope_jobs(manager, interaction)
        except Exception:
            return PomodoroPauseResult(
                ok=False,
                message="Something went wrong while fetching pomodoros.",
            )

        user_id = str(interaction.user.id)
        user_jobs = [
            job
            for job in jobs
            if job.type == "pomodoro" and str((job.data or {}).get("user")) == user_id
        ]
        if not user_jobs:
            return PomodoroPauseResult(
                ok=False,
                message=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )

        selected_job, selected_end_time = (
            PomodoroFunctions._select_user_job_by_pause_state(
                user_jobs,
                paused=False,
            )
        )
        if selected_job is None or selected_end_time is None:
            return PomodoroPauseResult(
                ok=False,
                message="Your pomodoro is already paused.",
            )

        now = datetime.datetime.now()
        remaining_seconds = max(
            0,
            math.ceil((selected_end_time - now).total_seconds()),
        )
        if remaining_seconds <= 0:
            return PomodoroPauseResult(
                ok=False,
                message="That pomodoro already finished or is about to finish.",
            )

        remaining_minutes = max(1, math.ceil(remaining_seconds / 60))
        total_duration_minutes = PomodoroFunctions._resolve_total_duration_minutes(
            selected_job.data,
            fallback=remaining_minutes,
        )
        mode = str((selected_job.data or {}).get("mode", "focus")).strip().lower()
        if mode not in ("focus", "break"):
            mode = "focus"

        try:
            update_result = await asyncio.to_thread(
                mongo_db["tasks"].update_one,
                {"_id": selected_job.id, "last_run": None},
                {
                    "$set": {
                        "data.paused": True,
                        "data.paused_remaining_seconds": remaining_seconds,
                        "data.paused_at": now.isoformat(),
                        "data.total_duration_minutes": str(total_duration_minutes),
                    }
                },
            )
        except Exception:
            return PomodoroPauseResult(
                ok=False,
                message="Something went wrong while pausing that pomodoro.",
            )

        if update_result.modified_count <= 0:
            return PomodoroPauseResult(
                ok=False,
                message="I couldn't pause that pomodoro. Please try again.",
            )

        await asyncio.to_thread(manager.fetch_jobs)

        if guild_id is not None:
            PomodoroVoiceManager.pause_for_guild(guild_id)

        return PomodoroPauseResult(
            ok=True,
            message=f"Paused with {remaining_minutes} minute(s) remaining.",
            mode=mode,
            duration_minutes=total_duration_minutes,
            remaining_minutes=remaining_minutes,
            remaining_seconds=remaining_seconds,
        )

    @staticmethod
    async def resume_user_pomodoro(
        interaction: discord.Interaction,
    ) -> PomodoroResumeResult:
        manager = DailyJobManager()
        guild_id = interaction.guild_id

        try:
            jobs = await PomodoroFunctions._list_scope_jobs(manager, interaction)
        except Exception:
            return PomodoroResumeResult(
                ok=False,
                message="Something went wrong while fetching pomodoros.",
            )

        user_id = str(interaction.user.id)
        user_jobs = [
            job
            for job in jobs
            if job.type == "pomodoro" and str((job.data or {}).get("user")) == user_id
        ]
        if not user_jobs:
            return PomodoroResumeResult(
                ok=False,
                message=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )

        selected_job, _ = PomodoroFunctions._select_user_job_by_pause_state(
            user_jobs,
            paused=True,
        )
        if selected_job is None:
            return PomodoroResumeResult(
                ok=False,
                message="Your pomodoro is already running.",
            )

        data = selected_job.data or {}
        remaining_seconds = PomodoroFunctions._safe_int(
            data.get("paused_remaining_seconds"),
            default=0,
        )
        if remaining_seconds <= 0:
            fallback_minutes = PomodoroFunctions._safe_int(
                data.get("duration"), default=0
            )
            remaining_seconds = max(0, fallback_minutes * 60)

        if remaining_seconds <= 0:
            return PomodoroResumeResult(
                ok=False,
                message="I couldn't resume that pomodoro because remaining time is missing.",
            )

        total_duration_minutes = PomodoroFunctions._resolve_total_duration_minutes(
            data,
            fallback=max(1, math.ceil(remaining_seconds / 60)),
        )
        new_end_time = (
            datetime.datetime.now() + datetime.timedelta(seconds=remaining_seconds)
        ).replace(microsecond=0)

        mode = str(data.get("mode", "focus")).strip().lower()
        if mode not in ("focus", "break"):
            mode = "focus"

        try:
            update_result = await asyncio.to_thread(
                mongo_db["tasks"].update_one,
                {"_id": selected_job.id, "last_run": None},
                {
                    "$set": {
                        "schedule.datetime": new_end_time.isoformat(),
                        "data.paused": False,
                        "data.duration": str(total_duration_minutes),
                        "data.total_duration_minutes": str(total_duration_minutes),
                    },
                    "$unset": {
                        "data.paused_remaining_seconds": "",
                        "data.paused_at": "",
                    },
                },
            )
        except Exception:
            return PomodoroResumeResult(
                ok=False,
                message="Something went wrong while resuming that pomodoro.",
            )

        if update_result.modified_count <= 0:
            return PomodoroResumeResult(
                ok=False,
                message="I couldn't resume that pomodoro. Please try again.",
            )

        await asyncio.to_thread(manager.fetch_jobs)

        if guild_id is not None:
            PomodoroVoiceManager.set_end_time_for_guild(guild_id, new_end_time)
            PomodoroVoiceManager.resume_for_guild(guild_id)

        return PomodoroResumeResult(
            ok=True,
            message="Pomodoro resumed.",
            mode=mode,
            end_time=new_end_time,
            duration_minutes=total_duration_minutes,
        )

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
        user_id = str(interaction.user.id)

        try:
            jobs = await PomodoroFunctions._list_scope_jobs(manager, interaction)
        except Exception:
            return PomodoroExtendResult(
                ok=False,
                message="Something went wrong while fetching pomodoros.",
            )

        user_jobs = [
            job
            for job in jobs
            if job.type == "pomodoro" and str((job.data or {}).get("user")) == user_id
        ]
        if not user_jobs:
            return PomodoroExtendResult(
                ok=False,
                message=(
                    "You don't have an active pomodoro "
                    f"{PomodoroFunctions._scope_message(interaction)}."
                ),
            )

        running_user_jobs = [
            job
            for job in user_jobs
            if not PomodoroFunctions._is_truthy((job.data or {}).get("paused"))
        ]
        if not running_user_jobs:
            return PomodoroExtendResult(
                ok=False,
                message="Resume the pomodoro before extending it.",
            )

        def _normalized(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
            if dt is None:
                return None
            if dt.tzinfo is not None and dt.utcoffset() is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt.replace(microsecond=0)

        normalized_expected = _normalized(expected_end_time)
        selected_job = None
        selected_job_end_time = None
        best_distance_seconds: Optional[float] = None

        for job in running_user_jobs:
            scheduled = PomodoroFunctions.parse_schedule_datetime(job.schedule)
            if scheduled is None:
                continue
            normalized_scheduled = _normalized(scheduled)
            if normalized_scheduled is None:
                continue
            if normalized_expected is None:
                if (
                    selected_job_end_time is None
                    or normalized_scheduled > selected_job_end_time
                ):
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

        current_duration = PomodoroFunctions._resolve_total_duration_minutes(
            selected_job.data
        )
        mode = str((selected_job.data or {}).get("mode", "focus")).strip().lower()
        if mode not in ("focus", "break"):
            mode = "focus"

        new_duration = max(0, current_duration) + minutes
        new_end_time = selected_job_end_time + datetime.timedelta(minutes=minutes)
        new_end_time = new_end_time.replace(microsecond=0)

        try:
            update_result = await asyncio.to_thread(
                mongo_db["tasks"].update_one,
                {"_id": selected_job.id, "last_run": None},
                {
                    "$set": {
                        "schedule.datetime": new_end_time.isoformat(),
                        "data.duration": str(new_duration),
                        "data.total_duration_minutes": str(new_duration),
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
            mode=mode,
        )
