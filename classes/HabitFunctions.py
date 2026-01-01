import datetime
import json
from typing import Optional, Tuple, Dict, Any, List

from bson.objectid import ObjectId
from openai import APIError, OpenAI

from classes.DailyJob import CronSchedule
from config.db import mongo_db
from config.env import env


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


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
        manager = DailyJobManager()
        manager.insert_job(
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
        text = reminder.strip()
        if not text:
            return None

        api_key = api_key or env.get("OPENAI_API_KEY")
        if not api_key:
            return None

        now = datetime.datetime.now()
        client = OpenAI(api_key=api_key)
        system_prompt = (
            "You convert natural language reminder times into 24-hour local times. "
            "Return JSON with a single key 'time' whose value is in HH:MM format. "
            "If the input cannot be understood, set 'time' to null. "
            "Ignore any dates and return the time only."
        )
        user_prompt = (
            f"Current local datetime: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"Input: {text}"
        )

        try:
            response = client.chat.completions.create(
                model=DEFAULT_OPENAI_MODEL,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
        except APIError:
            return None

        message = response.choices[0].message.content or ""
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return None

        time_value = payload.get("time")
        if not time_value:
            return None

        try:
            parsed = datetime.datetime.strptime(time_value.strip(), "%H:%M")
        except ValueError:
            return None

        return datetime.time(hour=parsed.hour, minute=parsed.minute)

    @staticmethod
    def insert_habit(
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
        user_id: int,
        channel_id: int,
        mode: str = "all",
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {
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
    def fetch_habit(habit_id: str) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(habit_id)
        except Exception:
            return None

        return mongo_db["habits"].find_one({"_id": object_id})

    @staticmethod
    def add_completion(habit_id: str, mode: str) -> bool:
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
            {"_id": object_id},
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
