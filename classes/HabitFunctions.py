import datetime
from typing import Optional, Tuple, Dict, Any, List

from bson.objectid import ObjectId

from classes.DailyJob import CronSchedule
from classes.OpenAIFunctions import OpenAIFunctions
from config.db import mongo_db
from config.env import settings


class HabitFunctions:
    @staticmethod
    def _normalize_scope(scope: Optional[str]) -> str:
        return scope if scope in ("channel", "personal") else "channel"

    @staticmethod
    def _channel_scope_query() -> Dict[str, Any]:
        return {
            "$or": [
                {"scope": "channel"},
                {"scope": {"$exists": False}},
                {"scope": None},
                {"scope": ""},
            ]
        }

    @staticmethod
    def insert_habit_task(
        habit: Dict[str, Any],
        reminder_time: datetime.time,
    ) -> None:
        from classes.DailyJobManager import DailyJobManager

        expression = f"{reminder_time.minute} {reminder_time.hour} * * *"
        schedule = CronSchedule(expression=expression)
        habit_id = str(habit.get("_id"))
        guild_id = habit.get("guild_id")
        manager = DailyJobManager()
        manager.insert_job(
            guild_id=guild_id,
            channel_id=habit.get("channel_id"),
            type="habit",
            data={"habit_id": habit_id},
            schedule=schedule,
        )

    @staticmethod
    def insert_habit(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        name: str,
        description: Optional[str] = None,
        reminder: Optional[str] = None,
        timezone: Optional[str] = None,
        scope: str = "channel",
    ) -> Tuple[Dict[str, Any], Optional[datetime.time]]:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Habit name cannot be empty.")

        scope_value = HabitFunctions._normalize_scope(scope)
        if guild_id is None:
            scope_value = "personal"

        cleaned_description = description.strip() if description else None
        if cleaned_description == "":
            cleaned_description = None

        reminder_time = None
        reminder_text = reminder.strip() if reminder else ""
        if reminder_text:
            api_key = settings.openai_api_key
            if not api_key:
                raise ValueError("OpenAI API key is not configured.")
            reminder_time = OpenAIFunctions.parse_reminder_time(
                reminder_text,
                api_key=api_key,
                timezone=timezone,
            )
            if reminder_time is None:
                raise ValueError(
                    "I couldn't understand that reminder time. Try '8am' or '20:30'."
                )

        document: Dict[str, Any] = {
            "scope": scope_value,
            "guild_id": None if scope_value == "personal" else guild_id,
            "user_id": user_id,
            "channel_id": None if scope_value == "personal" else channel_id,
            "name": cleaned_name,
            "description": cleaned_description,
            "created": datetime.datetime.now().isoformat(),
            "completitions": [],
        }

        result = mongo_db["habits"].insert_one(document)
        document["_id"] = result.inserted_id

        return document, reminder_time

    @staticmethod
    def list_habits(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        mode: str = "all",
        scope: str = "channel",
    ) -> List[Dict[str, Any]]:
        scope_value = HabitFunctions._normalize_scope(scope)
        if guild_id is None:
            scope_value = "personal"

        query: Dict[str, Any]
        if scope_value == "personal":
            query = {
                "scope": "personal",
                "user_id": user_id,
            }
        else:
            query = {
                "guild_id": guild_id,
                "user_id": user_id,
                "channel_id": channel_id,
                **HabitFunctions._channel_scope_query(),
            }
        cursor = mongo_db["habits"].find(query).sort("_id", 1)
        habits = list(cursor)

        if mode == "incomplete":
            habits = [
                habit for habit in habits if HabitFunctions.needs_completion_today(habit)
            ]

        return habits

    @staticmethod
    def fetch_habit(
        habit_id: str,
        guild_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(habit_id)
        except Exception:
            return None

        habit = mongo_db["habits"].find_one({"_id": object_id})
        if habit is None:
            return None

        scope_value = HabitFunctions._normalize_scope(
            str(habit.get("scope") or "channel")
        )
        if user_id is not None and int(habit.get("user_id") or 0) != int(user_id):
            return None
        if (
            scope_value == "channel"
            and guild_id is not None
            and habit.get("guild_id") != guild_id
        ):
            return None

        return habit

    @staticmethod
    def add_completion(
        habit_id: str,
        guild_id: Optional[int],
        mode: str,
        user_id: Optional[int] = None,
    ) -> bool:
        if mode not in {"complete", "skip", "incomplete"}:
            return False

        habit = HabitFunctions.fetch_habit(
            habit_id,
            guild_id=guild_id,
            user_id=user_id,
        )
        if habit is None:
            return False

        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "mode": mode,
        }

        result = mongo_db["habits"].update_one(
            {"_id": habit["_id"]},
            {"$push": {"completitions": entry}},
        )

        return result.modified_count > 0

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime.datetime]:
        if isinstance(value, datetime.datetime):
            dt = value
        elif isinstance(value, str):
            try:
                dt = datetime.datetime.fromisoformat(value)
            except ValueError:
                return None
        else:
            return None

        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)

        return dt

    @staticmethod
    def today_status(habit: Dict[str, Any]) -> Optional[str]:
        completions = habit.get("completitions", [])
        if not isinstance(completions, list) or not completions:
            return None

        today = datetime.datetime.now().date()
        latest_dt: Optional[datetime.datetime] = None
        latest_mode: Optional[str] = None

        for entry in completions:
            if not isinstance(entry, dict):
                continue
            mode = entry.get("mode")
            timestamp = entry.get("timestamp")
            if not mode or not timestamp:
                continue
            parsed = HabitFunctions._parse_timestamp(timestamp)
            if parsed is None or parsed.date() != today:
                continue
            if latest_dt is None or parsed > latest_dt:
                latest_dt = parsed
                latest_mode = str(mode)

        return latest_mode

    @staticmethod
    def needs_completion_today(habit: Dict[str, Any]) -> bool:
        status = HabitFunctions.today_status(habit)
        return status not in {"complete", "skip"}

    @staticmethod
    def recent_progress(habit: Dict[str, Any], days: int = 5) -> List[str]:
        days = max(1, days)
        today = datetime.datetime.now().date()
        created_value = habit.get("created")
        created_dt = HabitFunctions._parse_timestamp(created_value)
        if created_dt is not None:
            days_since_created = (today - created_dt.date()).days
            days = max(1, min(days, days_since_created + 1))

        completions = habit.get("completitions", [])
        day_status: Dict[datetime.date, Tuple[datetime.datetime, str]] = {}

        if isinstance(completions, list):
            for entry in completions:
                if not isinstance(entry, dict):
                    continue
                mode = entry.get("mode")
                timestamp = entry.get("timestamp")
                if not mode or not timestamp:
                    continue
                parsed = HabitFunctions._parse_timestamp(timestamp)
                if parsed is None:
                    continue
                day = parsed.date()
                if day < today - datetime.timedelta(days=days - 1) or day > today:
                    continue
                existing = day_status.get(day)
                if existing is None or parsed > existing[0]:
                    day_status[day] = (parsed, str(mode))

        progress: List[str] = []
        for offset in range(days - 1, -1, -1):
            day = today - datetime.timedelta(days=offset)
            status = day_status.get(day)
            if status:
                progress.append(status[1])
            else:
                progress.append("incomplete")

        return progress
