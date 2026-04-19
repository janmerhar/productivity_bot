import datetime
from typing import Optional, Tuple, Dict, Any, List, Mapping

from bson.objectid import ObjectId

from classes.DailyJobManager import DailyJobManager
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
    def _scope_query(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        scope: str = "channel",
    ) -> Dict[str, Any]:
        scope_value = HabitFunctions._normalize_scope(scope)
        if guild_id is None:
            scope_value = "personal"

        if scope_value == "personal":
            return {
                "scope": "personal",
                "user_id": user_id,
            }

        return {
            "guild_id": guild_id,
            "user_id": user_id,
            "channel_id": channel_id,
            **HabitFunctions._channel_scope_query(),
        }

    @staticmethod
    def insert_habit_task(
        habit: Dict[str, Any],
        reminder_time: datetime.time,
    ) -> None:
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
    def _parse_habit_reminder_time(
        reminder: Optional[str],
        timezone: Optional[str] = None,
    ) -> Optional[datetime.time]:
        reminder_text = reminder.strip() if reminder else ""
        if not reminder_text:
            return None

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

        return reminder_time

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

        reminder_time = HabitFunctions._parse_habit_reminder_time(
            reminder,
            timezone,
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
    def update_habit(
        habit_id: str,
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        name: str,
        description: Optional[str] = None,
        reminder: Optional[str] = None,
        timezone: Optional[str] = None,
        scope: str = "channel",
    ) -> Tuple[Optional[Dict[str, Any]], Optional[datetime.time]]:
        habit = HabitFunctions.fetch_habit(
            habit_id,
            guild_id=guild_id,
            user_id=user_id,
        )
        if habit is None:
            return None, None

        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Habit name cannot be empty.")

        scope_value = HabitFunctions._normalize_scope(scope)
        if guild_id is None:
            scope_value = "personal"

        cleaned_description = description.strip() if description else None
        if cleaned_description == "":
            cleaned_description = None

        reminder_time = HabitFunctions._parse_habit_reminder_time(
            reminder,
            timezone,
        )

        updated_fields: Dict[str, Any] = {
            "scope": scope_value,
            "guild_id": None if scope_value == "personal" else guild_id,
            "channel_id": None if scope_value == "personal" else channel_id,
            "name": cleaned_name,
            "description": cleaned_description,
        }

        mongo_db["habits"].update_one(
            {"_id": habit["_id"]},
            {"$set": updated_fields},
        )

        updated_habit = mongo_db["habits"].find_one({"_id": habit["_id"]})
        return updated_habit, reminder_time

    @staticmethod
    def delete_habit(
        habit_id: str,
        guild_id: Optional[int],
        user_id: Optional[int] = None,
    ) -> bool:
        habit = HabitFunctions.fetch_habit(
            habit_id,
            guild_id=guild_id,
            user_id=user_id,
        )
        if habit is None:
            return False

        habit_jobs = HabitFunctions.list_habit_tasks(
            habit_id,
            habit.get("guild_id"),
        )
        deleted = mongo_db["habits"].delete_one({"_id": habit["_id"]})
        if deleted.deleted_count <= 0:
            return False

        manager = DailyJobManager()
        for job in habit_jobs:
            try:
                manager.delete_job(str(job.id), guild_id=job.guild_id)
            except Exception:
                continue

        return True

    @staticmethod
    def fetch_habit_in_scope(
        habit_id: str,
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        scope: str = "channel",
    ) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(habit_id)
        except Exception:
            return None

        query = HabitFunctions._scope_query(
            guild_id,
            user_id,
            channel_id,
            scope,
        )
        query["_id"] = object_id
        return mongo_db["habits"].find_one(query)

    @staticmethod
    def find_habits_by_name(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        name: str,
        scope: str = "channel",
    ) -> List[Dict[str, Any]]:
        normalized_name = " ".join(str(name or "").strip().lower().split())
        if not normalized_name:
            return []

        query = HabitFunctions._scope_query(
            guild_id,
            user_id,
            channel_id,
            scope,
        )
        habits = list(mongo_db["habits"].find(query).sort("_id", 1))
        return [
            habit
            for habit in habits
            if " ".join(str(habit.get("name") or "").strip().lower().split())
            == normalized_name
        ]

    @staticmethod
    def autocomplete_habits(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        query: str,
        scope: str = "channel",
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        resolved_limit = max(1, min(limit, 25))
        normalized_query = " ".join(str(query or "").strip().lower().split())
        mongo_query = HabitFunctions._scope_query(
            guild_id,
            user_id,
            channel_id,
            scope,
        )
        habits = list(
            mongo_db["habits"]
            .find(mongo_query)
            .sort("_id", -1)
            .limit(200)
        )

        if not normalized_query:
            return habits[:resolved_limit]

        matches: List[Dict[str, Any]] = []
        for habit in habits:
            habit_name = " ".join(str(habit.get("name") or "").strip().lower().split())
            if normalized_query in habit_name:
                matches.append(habit)
            if len(matches) >= resolved_limit:
                break

        return matches

    @staticmethod
    def list_habits(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        mode: str = "all",
        scope: str = "channel",
    ) -> List[Dict[str, Any]]:
        query = HabitFunctions._scope_query(
            guild_id,
            user_id,
            channel_id,
            scope,
        )
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
    def _habit_task_matches(
        data: Optional[Mapping[str, Any]],
        habit_id: str,
    ) -> bool:
        return str((data or {}).get("habit_id") or "") == str(habit_id)

    @staticmethod
    def list_habit_tasks(
        habit_id: str,
        guild_id: Optional[int] = None,
    ) -> List[Any]:
        manager = DailyJobManager()
        jobs = manager.list_jobs(guild_id=guild_id)
        return [
            job
            for job in jobs
            if job.type == "habit"
            and HabitFunctions._habit_task_matches(job.data, habit_id)
        ]

    @staticmethod
    def get_habit_reminder_time(
        habit_id: str,
        guild_id: Optional[int] = None,
    ) -> Optional[datetime.time]:
        jobs = HabitFunctions.list_habit_tasks(habit_id, guild_id)
        if not jobs:
            return None

        schedule = jobs[0].schedule
        if not isinstance(schedule, Mapping):
            return None

        expression = str(schedule.get("expression") or "").strip()
        parts = expression.split()
        if len(parts) < 2:
            return None

        try:
            minute = int(parts[0])
            hour = int(parts[1])
            return datetime.time(hour=hour, minute=minute)
        except ValueError:
            return None

    @staticmethod
    def sync_habit_tasks(
        habit: Dict[str, Any],
        reminder_time: Optional[datetime.time],
    ) -> None:
        manager = DailyJobManager()
        habit_id = str(habit.get("_id") or "")
        guild_id = habit.get("guild_id")

        for job in HabitFunctions.list_habit_tasks(habit_id, guild_id):
            manager.delete_job(str(job.id), guild_id=job.guild_id)

        if reminder_time is not None:
            HabitFunctions.insert_habit_task(habit, reminder_time)

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
