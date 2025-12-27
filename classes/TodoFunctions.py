import datetime
import json
from typing import Optional, Tuple, Dict, Any, List

from openai import APIError, OpenAI
from bson.objectid import ObjectId

from classes.DailyJob import OneTimeSchedule2
from config.db import mongo_db
from config.env import env


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class TodoFunctions:
    @staticmethod
    def insert_todo_task(
        todo: Dict[str, Any],
        due_dt: datetime.datetime,
    ) -> None:
        from classes.DailyJobManager import DailyJobManager

        schedule = OneTimeSchedule2(datetime=due_dt.isoformat())
        task_id = str(todo.get("_id"))
        manager = DailyJobManager()
        manager.insert_job(
            channel_id=todo["channel_id"],
            type="todo",
            data={"task_id": task_id},
            schedule=schedule,
        )

    @staticmethod
    def convert_due_to_timestamp(
        due: str,
        api_key: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        text = due.strip()
        if not text:
            return None

        api_key = api_key or env.get("OPENAI_API_KEY")
        if not api_key:
            return None

        now = datetime.datetime.now()
        client = OpenAI(api_key=api_key)
        system_prompt = (
            "You convert natural language due dates into local datetimes. "
            "Return JSON with a single key 'due' whose value is an ISO 8601 datetime "
            "without timezone (YYYY-MM-DDTHH:MM). "
            "If the input cannot be understood, set 'due' to null. "
            "Prefer future dates; if a time would be in the past, choose the next occurrence."
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

        due_value = payload.get("due")
        if not due_value:
            return None

        try:
            due_dt = datetime.datetime.fromisoformat(due_value)
        except ValueError:
            return None

        if due_dt.tzinfo is not None:
            due_dt = due_dt.astimezone().replace(tzinfo=None)

        due_dt = due_dt.replace(second=0, microsecond=0)
        if due_dt <= now:
            due_dt += datetime.timedelta(days=1)

        return due_dt

    @staticmethod
    def insert_todo(
        user_id: int,
        channel_id: int,
        name: str,
        description: Optional[str] = None,
        due: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[datetime.datetime]]:
        cleaned_name = name.strip()
        if not cleaned_name:
            raise ValueError("Task name cannot be empty.")

        cleaned_description = description.strip() if description else None
        if cleaned_description == "":
            cleaned_description = None

        due_dt = None
        due_text = due.strip() if due else ""
        if due_text:
            api_key = env.get("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OpenAI API key is not configured.")
            due_dt = TodoFunctions.convert_due_to_timestamp(due_text, api_key=api_key)
            if due_dt is None:
                raise ValueError(
                    "I couldn't understand that due time. Try 'tomorrow 8pm'."
                )

        document: Dict[str, Any] = {
            "user_id": user_id,
            "channel_id": channel_id,
            "name": cleaned_name,
            "description": cleaned_description,
            "due": due_dt.isoformat() if due_dt else None,
            "state": "todo",
        }

        result = mongo_db["todos"].insert_one(document)
        document["_id"] = result.inserted_id

        return document, due_dt

    @staticmethod
    def list_todos(
        channel_id: int,
        mode: str = "channel",
        sort: str = "descending",
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"state": "todo"}
        if mode != "all":
            query["channel_id"] = channel_id

        sort_direction = -1 if sort == "descending" else 1
        cursor = mongo_db["todos"].find(query).sort("_id", sort_direction)

        return list(cursor)

    @staticmethod
    def fetch_todo(todo_id: str) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return None

        return mongo_db["todos"].find_one({"_id": object_id})

    @staticmethod
    def complete_todo(todo_id: str) -> bool:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return False

        result = mongo_db["todos"].update_one(
            {"_id": object_id},
            {"$set": {"state": "done"}},
        )

        return result.modified_count > 0
