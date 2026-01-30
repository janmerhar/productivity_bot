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
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        name: str,
        description: Optional[str] = None,
        due: Optional[str] = None,
        scope: str = "channel",
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

        scope_value = scope if scope in ("channel", "personal") else "channel"
        stored_guild_id = None if scope_value == "personal" else guild_id
        stored_channel_id = None if scope_value == "personal" else channel_id

        document: Dict[str, Any] = {
            "guild_id": stored_guild_id,
            "user_id": user_id,
            "channel_id": stored_channel_id,
            "name": cleaned_name,
            "description": cleaned_description,
            "due": due_dt.isoformat() if due_dt else None,
            "state": "todo",
            "scope": scope_value,
        }

        result = mongo_db["todos"].insert_one(document)
        document["_id"] = result.inserted_id

        return document, due_dt

    @staticmethod
    def list_todos(
        guild_id: Optional[int],
        channel_id: Optional[int],
        user_id: Optional[int] = None,
        mode: str = "channel",
        sort: str = "descending",
    ) -> List[Dict[str, Any]]:
        if mode == "personal":
            if user_id is None:
                return []
            query: Dict[str, Any] = {"state": "todo", "scope": "personal"}
            query["user_id"] = user_id
        else:
            query = {
                "state": "todo",
                "guild_id": guild_id,
                "scope": {"$ne": "personal"},
            }
            if mode != "all":
                query["channel_id"] = channel_id

        sort_direction = -1 if sort == "descending" else 1
        cursor = mongo_db["todos"].find(query).sort("_id", sort_direction)

        return list(cursor)

    @staticmethod
    def fetch_todo(
        todo_id: str, guild_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return None

        query: Dict[str, Any] = {"_id": object_id}
        if guild_id is not None:
            query["guild_id"] = guild_id
        return mongo_db["todos"].find_one(query)

    @staticmethod
    def complete_todo(
        todo_id: str,
        guild_id: Optional[int] = None,
        user_id: Optional[int] = None,
    ) -> bool:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return False

        if user_id is not None:
            result = mongo_db["todos"].update_one(
                {
                    "_id": object_id,
                    "user_id": user_id,
                    "scope": "personal",
                },
                {"$set": {"state": "done"}},
            )
            if result.modified_count > 0:
                return True

        if guild_id is None:
            return False

        result = mongo_db["todos"].update_one(
            {
                "_id": object_id,
                "guild_id": guild_id,
                "scope": {"$ne": "personal"},
            },
            {"$set": {"state": "done"}},
        )

        return result.modified_count > 0
