import datetime
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from embeds.PomodoroEmbeds import PomodoroEmbeds
from classes.DailyJob import DailyJob, OneTimeSchedule2


class PomodoroFunctions:
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
