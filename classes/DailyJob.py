import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from croniter import CroniterBadCronError, croniter

from config.db import mongo_db


@dataclass
class OneTimeSchedule:
    hour: int
    minute: int
    mode: Literal["one-time"] = "one-time"


@dataclass
class OneTimeSchedule2:
    datetime: str
    mode: Literal["one-time"] = "one-time"


@dataclass
class CronSchedule:
    expression: str
    mode: Literal["cron"] = "cron"


ScheduleConfig = Union[OneTimeSchedule, CronSchedule]


class DailyJob:
    def __init__(
        self,
        id: Optional[Any],
        channel_id: int,
        type: str,
        data: Dict[str, Any],
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]] = None,
        last_run: Optional[datetime.date] = None,
    ) -> None:
        self.id = id
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
        if self.id is not None:
            payload["id"] = self.id
        if isinstance(self.schedule, (OneTimeSchedule, CronSchedule)):
            payload["schedule"] = asdict(self.schedule)
        elif isinstance(self.schedule, Mapping):
            payload["schedule"] = dict(self.schedule)
        else:
            payload["schedule"] = None
        return payload

    def is_due(self, moment: datetime.datetime) -> bool:
        schedule = self.schedule
        if not isinstance(schedule, OneTimeSchedule):
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
                schedule = {"mode": "one-time", "hour": hour, "minute": minute}

        doc_id = doc.get("id")
        if doc_id is None:
            mongo_id = doc.get("_id")
            if mongo_id is not None:
                doc_id = str(mongo_id)

        return DailyJob(
            id=doc_id,
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

        if isinstance(raw_schedule, (OneTimeSchedule, CronSchedule)):
            return raw_schedule

        if isinstance(raw_schedule, Mapping):
            mode = raw_schedule.get("mode")

            if mode in ("one-time", "daily"):
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
                    return OneTimeSchedule(hour=int(hour), minute=int(minute))
                except (TypeError, ValueError):
                    return None

            if mode == "cron":
                expression = raw_schedule.get("expression") or raw_schedule.get("cron")
                if not expression:
                    return None
                return CronSchedule(expression=str(expression))

        return None

    def insert(
        channel_id: int,
        type: str,
        data: dict,
        schedule: dict = None,
    ) -> "DailyJob":
        document = {
            "channel_id": channel_id,
            "type": type,
            "data": data,
            "schedule": schedule,
            "last_run": None,
        }

        collection = mongo_db["tasks"]
        result = collection.insert_one(document)

        return DailyJob(
            id=str(result.inserted_id),
            channel_id=channel_id,
            type=type,
            data=data,
            schedule=schedule,
            last_run=None,
        )

    def is_due(self, check_datetime: datetime.datetime) -> bool:
        if isinstance(self.schedule, OneTimeSchedule2):
            if self.last_run is not None:
                return False

            # check if datetime matches scheduled datetime
            scheduled_dt = check_datetime.datetime.fromisoformat(self.schedule.datetime)
            return (
                check_datetime.year == scheduled_dt.year
                and check_datetime.month == scheduled_dt.month
                and check_datetime.day == scheduled_dt.day
                and check_datetime.hour == scheduled_dt.hour
                and check_datetime.minute == scheduled_dt.minute
            )

        elif isinstance(self.schedule, CronSchedule):
            if not croniter.match(self.schedule.expression, check_datetime):
                return False

            run_minute = check_datetime.replace(second=0, microsecond=0)
            last_run_value = self.last_run
            last_run_minute = last_run_value.replace(second=0, microsecond=0)

            if last_run_minute == run_minute:
                return False

            return True
        # check if current time matches schedule

        return False
    @staticmethod
    def fetch_cron_jobs() -> List["DailyJob"]:
        collection = mongo_db["task"]
        cursor = collection.find({"schedule.mode": "cron"})
        jobs: List[DailyJob] = []

        for doc in cursor:
            jobs.append(
                DailyJob(
                    id=doc.get("id"),
                    channel_id=doc["channel_id"],
                    type=doc.get("type", ""),
                    data=doc.get("data", {}),
                    schedule=doc.get("schedule"),
                    last_run=doc.get("last_run"),
                )
            )

        return jobs

    @staticmethod
    def fetch_one_time_jobs() -> List["DailyJob"]:
        collection = mongo_db["task"]
        cursor = collection.find({"schedule.mode": "one-time", "last_run": None})

        jobs: List[DailyJob] = []

        for doc in cursor:
            jobs.append(
                DailyJob(
                    id=doc.get("id"),
                    channel_id=doc["channel_id"],
                    type=doc.get("type", ""),
                    data=doc.get("data", {}),
                    schedule=doc.get("schedule"),
                    last_run=doc.get("last_run"),
                )
            )

        return jobs
