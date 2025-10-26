import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, Literal, Mapping, Optional, Union


@dataclass
class DailySchedule:
    hour: int
    minute: int
    mode: Literal["daily"] = "daily"


@dataclass
class CronSchedule:
    expression: str
    mode: Literal["cron"] = "cron"


ScheduleConfig = Union[DailySchedule, CronSchedule]


class DailyJob:
    def __init__(
        self,
        channel_id: int,
        type: str,
        data: Dict[str, Any],
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]] = None,
        last_run: Optional[datetime.date] = None,
    ) -> None:
        self.channel_id = channel_id
        self.type = type
        self.data = data
        self.schedule = self._normalize_schedule(schedule)
        self.last_run = last_run

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "channel_id": self.channel_id,
            "type": self.type,
            "data": self.data,
            "last_run": self.last_run,
        }
        if isinstance(self.schedule, (DailySchedule, CronSchedule)):
            payload["schedule"] = asdict(self.schedule)
        elif isinstance(self.schedule, Mapping):
            payload["schedule"] = dict(self.schedule)
        else:
            payload["schedule"] = None
        return payload

    def is_due(self, moment: datetime.datetime) -> bool:
        schedule = self.schedule
        if not isinstance(schedule, DailySchedule):
            return False
        if schedule.hour != moment.hour or schedule.minute != moment.minute:
            return False
        return self.last_run != moment.date()

    def mark_ran(self, moment: datetime.datetime) -> None:
        self.last_run = moment.date()

    @staticmethod
    def from_document(doc: Mapping[str, Any]) -> "DailyJob":
        schedule = doc.get("schedule")
        if not schedule:
            hour = doc.get("hour")
            minute = doc.get("minute")
            if hour is not None and minute is not None:
                schedule = {"mode": "daily", "hour": hour, "minute": minute}

        return DailyJob(
            channel_id=doc["channel_id"],
            type=doc.get("type") or doc.get("kind", ""),
            data=doc.get("data", {}),
            schedule=schedule,
            last_run=doc.get("last_run"),
        )

    @staticmethod
    def _normalize_schedule(
        raw_schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]],
    ) -> Optional[ScheduleConfig]:
        if raw_schedule is None:
            return None

        if isinstance(raw_schedule, (DailySchedule, CronSchedule)):
            return raw_schedule

        if isinstance(raw_schedule, Mapping):
            mode = raw_schedule.get("mode")

            if mode == "daily":
                hour = raw_schedule.get("hour")
                minute = raw_schedule.get("minute")
                if hour is None or minute is None:
                    time_info = raw_schedule.get("time")
                    if isinstance(time_info, Mapping):
                        hour = time_info.get("hour")
                        minute = time_info.get("minute")
                if hour is None or minute is None:
                    return None
                try:
                    return DailySchedule(hour=int(hour), minute=int(minute))
                except (TypeError, ValueError):
                    return None

            if mode == "cron":
                expression = raw_schedule.get("expression") or raw_schedule.get("cron")
                if not expression:
                    return None
                return CronSchedule(expression=str(expression))

        return None
