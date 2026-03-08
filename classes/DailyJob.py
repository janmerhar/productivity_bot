import datetime
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Literal, Mapping, Optional, Union
from bson.objectid import ObjectId
import discord
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
    @staticmethod
    def _is_paused(data: Optional[Mapping[str, Any]]) -> bool:
        paused_value = (data or {}).get("paused")
        if isinstance(paused_value, str):
            paused_value = paused_value.strip().lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
        return bool(paused_value)

    @staticmethod
    def _parse_expiration(data: Optional[Mapping[str, Any]]) -> Optional[datetime.datetime]:
        raw_value = str((data or {}).get("expires_at") or "").strip()
        if not raw_value:
            return None

        try:
            return datetime.datetime.fromisoformat(raw_value)
        except ValueError:
            return None

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
    def fetch_by_id(
        job_id: ObjectId,
        channel_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> Optional["DailyJob"]:
        filter_query: Dict[str, Any] = {"_id": job_id}
        if channel_id is not None:
            filter_query["channel_id"] = channel_id
        if guild_id is not None:
            filter_query["guild_id"] = guild_id

        doc = mongo_db["tasks"].find_one(filter_query)
        if not doc:
            return None

        return DailyJob(
            id=doc["_id"],
            guild_id=doc.get("guild_id"),
            channel_id=doc["channel_id"],
            type=doc["type"],
            data=doc["data"],
            schedule=doc["schedule"],
            last_run=doc["last_run"],
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

    @staticmethod
    def update(
        job_id: ObjectId,
        data: Optional[Dict[str, Any]] = None,
        schedule: Optional[Union[ScheduleConfig, Mapping[str, Any]]] = None,
        new_channel_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        guild_id: Optional[int] = None,
    ) -> bool:
        filter_query: Dict[str, Any] = {"_id": job_id}
        if channel_id is not None:
            filter_query["channel_id"] = channel_id
        if guild_id is not None:
            filter_query["guild_id"] = guild_id

        set_fields: Dict[str, Any] = {}
        if data is not None:
            set_fields["data"] = data
        if schedule is not None:
            if isinstance(schedule, Mapping):
                set_fields["schedule"] = dict(schedule)
            else:
                set_fields["schedule"] = asdict(schedule)
        if new_channel_id is not None:
            set_fields["channel_id"] = new_channel_id

        if not set_fields:
            return False

        result = mongo_db["tasks"].update_one(
            filter_query,
            {"$set": set_fields},
        )
        return result.matched_count > 0

    def is_due(self, check_datetime: datetime.datetime) -> bool:
        expires_at = self._parse_expiration(self.data)
        if expires_at is not None:
            if check_datetime.replace(second=0, microsecond=0) > expires_at.replace(
                second=0,
                microsecond=0,
            ):
                return False

        if self._is_paused(self.data):
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
            payload: Dict[str, Any] = {}
            content = str(self.data.get("message") or "").strip()
            if content:
                payload["content"] = content

            embed_data = self.data.get("embed")
            if isinstance(embed_data, Mapping):
                embed = discord.Embed(
                    title=str(embed_data.get("title") or "").strip() or None,
                    description=str(embed_data.get("description") or "").strip() or None,
                )
                thumbnail_url = str(embed_data.get("thumbnail_url") or "").strip()
                if thumbnail_url:
                    embed.set_thumbnail(url=thumbnail_url)
                payload["embed"] = embed

            return payload

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
