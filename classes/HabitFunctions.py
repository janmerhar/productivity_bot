import datetime
from typing import Optional, Tuple, Dict, Any, List

from bson.objectid import ObjectId

from classes.DailyJob import CronSchedule
from classes.OpenAIFunctions import OpenAIFunctions
from config.db import mongo_db
from config.env import env


class HabitFunctions:
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
            channel_id=habit["channel_id"],
            type="habit",
            data={"habit_id": habit_id},
            schedule=schedule,
        )

    @staticmethod
    def convert_reminder_to_time(
        reminder: str,
        api_key: Optional[str] = None,
    ) -> Optional[datetime.time]:
        return OpenAIFunctions.parse_reminder_time(reminder, api_key=api_key)

    @staticmethod
    def insert_habit(
        guild_id: int,
        user_id: int,
        channel_id: int,
        name: str,
        description: Optional[str] = None,
        reminder: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[datetime.time]]:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Habit name cannot be empty.")

        cleaned_description = description.strip() if description else None
        if cleaned_description == "":
            cleaned_description = None

        reminder_time = None
        reminder_text = reminder.strip() if reminder else ""
        if reminder_text:
            api_key = env.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key is not configured.")
            reminder_time = HabitFunctions.convert_reminder_to_time(
                reminder_text,
                api_key=api_key,
            )
            if reminder_time is None:
                raise ValueError(
                    "I couldn't understand that reminder time. Try '8am' or '20:30'."
                )

        document: Dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "channel_id": channel_id,
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
        guild_id: int,
        user_id: int,
        channel_id: int,
        mode: str = "all",
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {
            "guild_id": guild_id,
            "user_id": user_id,
            "channel_id": channel_id,
        }
        cursor = mongo_db["habits"].find(query).sort("_id", 1)
        habits = list(cursor)

        if mode == "incomplete":
            habits = [
                habit for habit in habits if HabitFunctions.needs_completion_today(habit)
            ]

        return habits

    @staticmethod
    def fetch_habit(habit_id: str, guild_id: int) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(habit_id)
        except Exception:
            return None

        return mongo_db["habits"].find_one({"_id": object_id, "guild_id": guild_id})

    @staticmethod
    def add_completion(habit_id: str, guild_id: int, mode: str) -> bool:
        if mode not in {"complete", "skip", "incomplete"}:
            return False

        try:
            object_id = ObjectId(habit_id)
        except Exception:
            return False

        entry = {
            "timestamp": datetime.datetime.now().isoformat(),
            "mode": mode,
        }

        result = mongo_db["habits"].update_one(
            {"_id": object_id, "guild_id": guild_id},
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
