import datetime
from typing import Any, Dict, Mapping, Optional, Tuple, Union

from classes.DailyJobManager import DailyJobManager
from embeds.PomodoroEmbeds import PomodoroEmbeds
from classes.DailyJob import DailyJob


class PomodoroFunctions:
    def insert_timer(
        self,
        channel_id: int,
        mode: str,
        duration: Optional[int],
        user_id: Union[int, str],
    ) -> Tuple[datetime.datetime, int]:
        manager = DailyJobManager()
        end_time, duration_minutes = manager.insert_pomodoro_timer(
            channel_id=channel_id,
            mode=mode,
            duration_minutes=duration,
            user_id=user_id,
        )

        return end_time, duration_minutes

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

    def pomodoro_payload(self, job: DailyJob) -> Dict[str, Any]:
        data = job.data or {}
        mode = str(data.get("mode", "focus")).lower()
        duration = data.get("duration", "")
        user_id = data.get("user")
        end_time = self.parse_schedule_datetime(job.schedule)

        return PomodoroEmbeds.timer_complete_embed(
            mode=mode,
            duration_minutes=duration,
            end_time=end_time,
            user_id=user_id,
        )
