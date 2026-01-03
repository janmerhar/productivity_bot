import datetime
from typing import Optional, Tuple, Dict, Any, List

from bson.objectid import ObjectId

from classes.DailyJob import OneTimeSchedule2
from classes.OpenAIFunctions import OpenAIFunctions
from config.db import mongo_db
from config.env import env


class TodoFunctions:
    @staticmethod
    def insert_todo_task(
        todo: Dict[str, Any],
        due_dt: datetime.datetime,
    ) -> None:
        from classes.DailyJobManager import DailyJobManager

        schedule = OneTimeSchedule2(datetime=due_dt.isoformat())
        task_id = str(todo.get("_id"))
        guild_id = todo.get("guild_id")
        manager = DailyJobManager()
        manager.insert_job(
            guild_id=guild_id,
            channel_id=todo["channel_id"],
            type="todo",
            data={"task_id": task_id},
            schedule=schedule,
        )

    @staticmethod
    def insert_todo(
        guild_id: int,
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
            due_dt = OpenAIFunctions.parse_due_datetime(due_text, api_key=api_key)
            if due_dt is None:
                raise ValueError(
                    "I couldn't understand that due time. Try 'tomorrow 8pm'."
                )

        document: Dict[str, Any] = {
            "guild_id": guild_id,
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
        guild_id: int,
        channel_id: int,
        mode: str = "channel",
        sort: str = "descending",
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"state": "todo", "guild_id": guild_id}
        if mode != "all":
            query["channel_id"] = channel_id

        sort_direction = -1 if sort == "descending" else 1
        cursor = mongo_db["todos"].find(query).sort("_id", sort_direction)

        return list(cursor)

    @staticmethod
    def fetch_todo(todo_id: str, guild_id: int) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return None

        return mongo_db["todos"].find_one({"_id": object_id, "guild_id": guild_id})

    @staticmethod
    def complete_todo(todo_id: str, guild_id: int) -> bool:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return False

        result = mongo_db["todos"].update_one(
            {"_id": object_id, "guild_id": guild_id},
            {"$set": {"state": "done"}},
        )

        return result.modified_count > 0
