import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal, Mapping, Optional, Union
from embeds.CryptoEmbeds import CryptoEmbeds
from embeds.StocksEmbeds import StocksEmbeds

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
        id: Any,
        channel_id: int,
        type: str,
        data: Dict[str, Any],
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]],
        last_run: Optional[datetime.date] = None,
    ) -> None:
        self.id = id
        self.channel_id = channel_id
        self.type = type
        self.data = data
        self.schedule = schedule
        self.last_run = last_run

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
            "schedule": asdict(schedule),
            "last_run": None,
        }

        collection = mongo_db["tasks"]
        result = collection.insert_one(document)

        return DailyJob(
            id=result.inserted_id,
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

    def run(self) -> Dict[str, Any]:
        now = datetime.datetime.utcnow()
        filter_query = {"_id": self.id}
        mongo_db["tasks"].update_one(filter_query, {"$set": {"last_run": now}})

        if self.type == "message":
            return {"content": self.data.get("message", "")}

        if self.type == "crypto":
            tickers = self.data["tickers"]
            currency = self.data.get("currency", "usd")
            raw_periods = self.data.get("change_periods", ("24h", "7d", "30d"))

            embeds, error = CryptoEmbeds().daily_embeds(tickers, currency, raw_periods)

            payload = {"embeds": embeds}
            header = self.data.get("header")
            if header:
                payload["content"] = header
            return payload

        if self.type == "stock":
            ticker = self.data["ticker"]
            embeds, error = StocksEmbeds().daily_embeds(ticker)

            payload = {"embeds": embeds}
            header = self.data.get("header")
            if header:
                payload["content"] = header

            return payload

        return {}

    @staticmethod
    def fetch_cron_jobs() -> List["DailyJob"]:
        collection = mongo_db["tasks"]
        cursor = collection.find({"schedule.mode": "cron"})
        jobs: List[DailyJob] = []

        for doc in cursor:
            jobs.append(
                DailyJob(
                    id=doc["_id"],
                    channel_id=doc["channel_id"],
                    type=doc["type"],
                    data=doc["data"],
                    schedule=doc["schedule"],
                    last_run=doc["last_run"],
                )
            )

        return jobs

    @staticmethod
    def fetch_one_time_jobs() -> List["DailyJob"]:
        collection = mongo_db["tasks"]
        cursor = collection.find({"schedule.mode": "one-time", "last_run": None})

        jobs: List[DailyJob] = []

        for doc in cursor:
            jobs.append(
                DailyJob(
                    id=doc["_id"],
                    channel_id=doc["channel_id"],
                    type=doc["type"],
                    data=doc["data"],
                    schedule=doc["schedule"],
                    last_run=doc["last_run"],
                )
            )

        return jobs
