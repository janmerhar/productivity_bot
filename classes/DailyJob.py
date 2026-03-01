import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal, Mapping, Optional, Union
from bson.objectid import ObjectId
from embeds.CryptoEmbeds import CryptoEmbeds
from embeds.StocksEmbeds import StocksEmbeds

from croniter import CroniterBadCronError, croniter

from config.db import mongo_db


@dataclass
class OneTimeSchedule2:
    datetime: str
    mode: Literal["one-time"] = "one-time"


@dataclass
class CronSchedule:
    expression: str
    mode: Literal["cron"] = "cron"


ScheduleConfig = Union[OneTimeSchedule2, CronSchedule]


class DailyJob:
    def __init__(
        self,
        id: ObjectId,
        guild_id: Optional[int],
        channel_id: Optional[int],
        type: str,
        data: Dict[str, Any],
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]],
        last_run: Optional[datetime.date] = None,
    ) -> None:
        self.id = id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.type = type
        self.data = data
        self.schedule = schedule
        self.last_run = last_run

    def insert(
        guild_id: Optional[int],
        channel_id: Optional[int],
        type: str,
        data: dict,
        schedule: dict = None,
    ) -> "DailyJob":
        document = {
            "guild_id": guild_id,
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
            guild_id=guild_id,
            channel_id=channel_id,
            type=type,
            data=data,
            schedule=schedule,
            last_run=None,
        )

    @staticmethod
    def delete(
        job_id: ObjectId,
        channel_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> bool:
        filter_query: Dict[str, Any] = {"_id": job_id}
        if channel_id is not None:
            filter_query["channel_id"] = channel_id
        if guild_id is not None:
            filter_query["guild_id"] = guild_id

        result = mongo_db["tasks"].delete_one(filter_query)
        return result.deleted_count > 0

    def is_due(self, check_datetime: datetime.datetime) -> bool:
        if self.type == "pomodoro":
            paused_value = (self.data or {}).get("paused")
            if isinstance(paused_value, str):
                paused_value = paused_value.strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                )
            if bool(paused_value):
                return False

        schedule = self.schedule

        if isinstance(schedule, Mapping):
            mode = schedule.get("mode")
        else:
            mode = getattr(schedule, "mode", None)

        if mode == "one-time":
            if self.last_run is not None:
                return False

            scheduled_dt = datetime.datetime.fromisoformat(schedule["datetime"])

            return scheduled_dt.replace(
                second=0, microsecond=0
            ) == check_datetime.replace(second=0, microsecond=0)

        if mode == "cron":
            expression = schedule["expression"]

            if not croniter.match(expression, check_datetime):
                return False

            run_minute = check_datetime.replace(second=0, microsecond=0)
            last_run_value = self.last_run

            if last_run_value is None:
                return True

            if not isinstance(last_run_value, datetime.datetime):
                return True

            last_run_minute = last_run_value.replace(second=0, microsecond=0)

            if last_run_minute == run_minute:
                return False

            return True

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

            embeds, error = CryptoEmbeds.daily_embeds(tickers, currency, raw_periods)

            payload = {"embeds": embeds}
            header = self.data.get("header")
            if header:
                payload["content"] = header
            return payload

        if self.type == "stock":
            symbol = str(self.data.get("ticker") or "").strip()
            if not symbol:
                return {}

            embeds, error = StocksEmbeds.daily_embeds(symbol)

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
                    guild_id=doc.get("guild_id"),
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
                    guild_id=doc.get("guild_id"),
                    channel_id=doc["channel_id"],
                    type=doc["type"],
                    data=doc["data"],
                    schedule=doc["schedule"],
                    last_run=doc["last_run"],
                )
            )

        return jobs
