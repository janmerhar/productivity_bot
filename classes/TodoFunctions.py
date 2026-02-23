import datetime
import re
from typing import Optional, Tuple, Dict, Any, List, Union

from bson.objectid import ObjectId
from pymongo import ReturnDocument

from classes.DailyJob import OneTimeSchedule2
from classes.OpenAIFunctions import OpenAIFunctions
from config.db import mongo_db
from config.env import env


class TodoFunctions:
    _MAX_LIST_NAME_LEN = 80
    _MAX_ITEM_TEXT_LEN = 800
    _MAX_TITLE_LEN = 100
    _ALLOWED_ITEM_STATUSES = {"todo", "in_progress", "done"}

    @staticmethod
    def _normalize_scope(scope: str) -> str:
        return scope if scope in ("channel", "personal") else "channel"

    @staticmethod
    def _parse_due_datetime(
        due: Optional[str],
        timezone: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        due_text = due.strip() if due else ""
        if not due_text:
            return None

        api_key = env.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key is not configured.")
        due_dt = OpenAIFunctions.parse_due_datetime(
            due_text,
            api_key=api_key,
            timezone=timezone,
        )
        if due_dt is None:
            raise ValueError(
                "I couldn't understand that due time. Try 'tomorrow 8pm'."
            )
        return due_dt

    @staticmethod
    def _clean_list_name(name: str) -> str:
        cleaned = name.strip()
        if not cleaned:
            raise ValueError("List name cannot be empty.")
        if len(cleaned) > TodoFunctions._MAX_LIST_NAME_LEN:
            raise ValueError(
                f"List name must be at most {TodoFunctions._MAX_LIST_NAME_LEN} characters."
            )
        return cleaned

    @staticmethod
    def _clean_item_text(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            raise ValueError("Item text cannot be empty.")
        if len(cleaned) > TodoFunctions._MAX_ITEM_TEXT_LEN:
            raise ValueError(
                f"Item text must be at most {TodoFunctions._MAX_ITEM_TEXT_LEN} characters."
            )
        return cleaned

    @staticmethod
    def _item_title_from_text(text: str) -> str:
        first_line = text.splitlines()[0].strip() if text else ""
        if not first_line:
            return "Untitled item"
        if len(first_line) <= TodoFunctions._MAX_TITLE_LEN:
            return first_line
        return first_line[: TodoFunctions._MAX_TITLE_LEN - 3].rstrip() + "..."

    @staticmethod
    def _normalize_item_status(status: str) -> str:
        normalized = status.strip().lower().replace(" ", "_")
        if normalized not in TodoFunctions._ALLOWED_ITEM_STATUSES:
            raise ValueError(
                "Invalid status. Use one of: todo, in_progress, done."
            )
        return normalized

    @staticmethod
    def _clean_item_title(title: str) -> str:
        cleaned = (title or "").strip()
        if not cleaned:
            raise ValueError("Task text cannot be empty.")
        if "\n" in cleaned or "\r" in cleaned:
            cleaned = cleaned.splitlines()[0].strip()
        if not cleaned:
            raise ValueError("Task text cannot be empty.")
        if len(cleaned) > TodoFunctions._MAX_TITLE_LEN:
            raise ValueError(
                f"Task text must be at most {TodoFunctions._MAX_TITLE_LEN} characters."
            )
        return cleaned

    @staticmethod
    def _clean_item_description(description: Optional[str]) -> Optional[str]:
        cleaned = (description or "").strip()
        if not cleaned:
            return None
        if len(cleaned) > TodoFunctions._MAX_ITEM_TEXT_LEN:
            raise ValueError(
                f"Description must be at most {TodoFunctions._MAX_ITEM_TEXT_LEN} characters."
            )
        return cleaned

    @staticmethod
    def _parse_due_input_value(due: Optional[str]) -> Optional[str]:
        due_text = (due or "").strip()
        if not due_text:
            return None

        try:
            return datetime.datetime.fromisoformat(due_text).isoformat()
        except ValueError:
            pass

        parsed = TodoFunctions._parse_due_datetime(due_text)
        return parsed.isoformat() if parsed else None

    @staticmethod
    def parse_assignee_modal_input(
        assignee: str,
        acting_user_id: int,
    ) -> Optional[int]:
        value = (assignee or "").strip()
        if not value:
            raise ValueError(
                "Assignee cannot be empty. Use `none`, `me`, a user ID, or a mention."
            )

        lowered = value.lower()
        if lowered in {"none", "unassign", "unassigned", "clear", "__none__"}:
            return None
        if lowered in {"me", "self", "__me__"}:
            return acting_user_id
        if value.startswith("user:"):
            return TodoFunctions.parse_assignee_token(value, acting_user_id)

        mention_match = re.fullmatch(r"<@!?(\d+)>", value)
        if mention_match:
            return int(mention_match.group(1))

        if value.startswith("@") and value[1:].isdigit():
            return int(value[1:])
        if value.isdigit():
            return int(value)

        raise ValueError(
            "Assignee must be `none`, `me`, a user ID, `user:<id>`, or a mention."
        )

    @staticmethod
    def _build_list_query(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        list_name: str,
        scope: str,
    ) -> Dict[str, Any]:
        name_key = list_name.lower()
        scope_value = TodoFunctions._normalize_scope(scope)
        if scope_value == "personal":
            return {
                "scope": "personal",
                "user_id": user_id,
                "name_key": name_key,
            }

        return {
            "scope": "channel",
            "guild_id": guild_id,
            "channel_id": channel_id,
            "name_key": name_key,
        }

    @staticmethod
    def _coerce_object_id(value: Any) -> Optional[ObjectId]:
        if isinstance(value, ObjectId):
            return value
        try:
            return ObjectId(value)
        except Exception:
            return None

    @staticmethod
    def trim_text(text: str, limit: int) -> str:
        if limit <= 0:
            return ""
        cleaned = text.strip()
        if len(cleaned) <= limit:
            return cleaned
        return cleaned[: max(0, limit - 3)].rstrip() + "..."

    @staticmethod
    def todo_from_message_fields(
        content: Optional[str],
        author_display_name: str,
        has_attachments: bool,
    ) -> Tuple[str, Optional[str]]:
        normalized_content = (content or "").strip()
        name_source = (
            normalized_content.splitlines()[0].strip() if normalized_content else ""
        )

        if not name_source:
            if has_attachments:
                name_source = f"Attachment from {author_display_name}"
            else:
                name_source = f"Message from {author_display_name}"

        name = TodoFunctions.trim_text(name_source, TodoFunctions._MAX_TITLE_LEN)
        description = (
            TodoFunctions.trim_text(normalized_content, TodoFunctions._MAX_ITEM_TEXT_LEN)
            if normalized_content
            else None
        )
        return name, description

    @staticmethod
    def insert_todo_from_message(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        channel_name: Optional[str],
        content: Optional[str],
        author_display_name: str,
        has_attachments: bool,
        scope: str,
    ) -> Dict[str, Any]:
        scope_value = TodoFunctions._normalize_scope(scope)
        if guild_id is None and scope_value != "personal":
            raise ValueError("That action can only be used in a server.")

        name, description = TodoFunctions.todo_from_message_fields(
            content,
            author_display_name,
            has_attachments,
        )
        if not name.strip():
            raise ValueError("I couldn't extract a todo title.")

        todo_list = TodoFunctions.get_or_create_implicit_list(
            guild_id,
            channel_id,
            user_id,
            channel_name,
            scope_value,
        )
        item_text = description if description else name
        document, _ = TodoFunctions.add_item_to_list(
            todo_list,
            user_id,
            item_text,
            None,
            "todo",
            None,
        )
        return document

    @staticmethod
    def fetch_todo_list_or_error(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        name: str,
        scope: str,
    ) -> Dict[str, Any]:
        todo_list = TodoFunctions.fetch_todo_list(
            guild_id=guild_id,
            user_id=user_id,
            channel_id=channel_id,
            name=name,
            scope=scope,
        )
        if not todo_list:
            raise ValueError(f"List `{name}` was not found in {scope} scope.")
        return todo_list

    @staticmethod
    def fetch_item_on_list_or_error(
        list_id: Any,
        item_no: int,
    ) -> Dict[str, Any]:
        if item_no <= 0:
            raise ValueError("Item number must be greater than 0.")
        item = TodoFunctions.fetch_item_on_list(list_id, item_no)
        if not item:
            raise ValueError(f"Item #{item_no} was not found on that list.")
        return item

    @staticmethod
    def _implicit_list_name(
        channel_name: Optional[str],
        channel_id: Optional[int],
    ) -> str:
        cleaned_name = (channel_name or "").strip()
        if cleaned_name:
            return TodoFunctions.trim_text(cleaned_name, TodoFunctions._MAX_LIST_NAME_LEN)
        if channel_id is not None:
            return f"channel-{channel_id}"
        return "direct-messages"

    @staticmethod
    def get_or_create_channel_list(
        guild_id: Optional[int],
        channel_id: Optional[int],
        user_id: int,
        channel_name: Optional[str],
    ) -> Dict[str, Any]:
        if channel_id is None:
            raise ValueError("Could not resolve the current channel.")

        scope_value = "channel" if guild_id is not None else "personal"
        list_name = TodoFunctions._implicit_list_name(channel_name, channel_id)
        name_key = list_name.lower()

        query: Dict[str, Any] = {
            "scope": scope_value,
            "guild_id": guild_id,
            "channel_id": channel_id,
        }
        existing = mongo_db["todo_lists"].find_one(query)
        if existing:
            updates: Dict[str, Any] = {}
            if existing.get("name") != list_name:
                updates["name"] = list_name
            if existing.get("name_key") != name_key:
                updates["name_key"] = name_key
            if updates:
                mongo_db["todo_lists"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": updates},
                )
                existing.update(updates)
            return existing

        document: Dict[str, Any] = {
            "name": list_name,
            "name_key": name_key,
            "scope": scope_value,
            "guild_id": guild_id,
            "channel_id": channel_id,
            "user_id": user_id,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }

        result = mongo_db["todo_lists"].insert_one(document)
        document["_id"] = result.inserted_id
        return document

    @staticmethod
    def get_or_create_implicit_list(
        guild_id: Optional[int],
        channel_id: Optional[int],
        user_id: int,
        channel_name: Optional[str],
        target: str,
    ) -> Dict[str, Any]:
        target_value = target.strip().lower()
        if target_value not in ("channel", "personal"):
            raise ValueError("Invalid list target.")

        if target_value == "channel":
            if guild_id is None:
                # In DMs there is no channel-scoped shared list; treat as personal.
                target_value = "personal"
            else:
                return TodoFunctions.get_or_create_channel_list(
                    guild_id=guild_id,
                    channel_id=channel_id,
                    user_id=user_id,
                    channel_name=channel_name,
                )

        # Personal implicit list is one list per user.
        query: Dict[str, Any] = {
            "scope": "personal",
            "user_id": user_id,
            "channel_id": None,
            "guild_id": None,
        }
        existing = mongo_db["todo_lists"].find_one(query)
        if existing:
            return existing

        document: Dict[str, Any] = {
            "name": "Personal",
            "name_key": "personal",
            "scope": "personal",
            "guild_id": None,
            "channel_id": None,
            "user_id": user_id,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }
        result = mongo_db["todo_lists"].insert_one(document)
        document["_id"] = result.inserted_id
        return document

    @staticmethod
    def parse_assignee_token(
        assignee: Optional[str],
        acting_user_id: int,
    ) -> Optional[int]:
        if assignee is None or assignee == "":
            return None
        if assignee == "__none__":
            return None
        if assignee == "__me__":
            return acting_user_id
        if assignee.startswith("user:"):
            raw_id = assignee.split(":", 1)[1].strip()
            try:
                return int(raw_id)
            except ValueError as exc:
                raise ValueError("Please select an assignee from autocomplete options.") from exc
        raise ValueError("Please select an assignee from autocomplete options.")

    @staticmethod
    def format_due(due: Optional[Union[datetime.datetime, str]]) -> str:
        if due is None:
            return "Not set"
        if isinstance(due, str):
            try:
                parsed = datetime.datetime.fromisoformat(due)
                return parsed.strftime("%Y-%m-%d %H:%M")
            except ValueError:
                return due
        return due.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def item_text(item: Dict[str, Any]) -> str:
        value = item.get("text") or item.get("description") or item.get("name") or ""
        return str(value).strip()

    @staticmethod
    def item_status(item: Dict[str, Any]) -> str:
        status = str(item.get("status") or "").strip().lower()
        if status in TodoFunctions._ALLOWED_ITEM_STATUSES:
            return status
        return "done" if item.get("state") == "done" else "todo"

    @staticmethod
    def status_label(status: str) -> str:
        labels = {
            "todo": "To Do",
            "in_progress": "In Progress",
            "done": "Done",
        }
        return labels.get(status, status)

    @staticmethod
    def truncate_multiline(text: str, limit: int = 220) -> str:
        normalized = " ".join(text.split())
        if len(normalized) <= limit:
            return normalized
        return normalized[: limit - 3].rstrip() + "..."

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

        due_dt = TodoFunctions._parse_due_datetime(due)
        scope_value = TodoFunctions._normalize_scope(scope)
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
            query: Dict[str, Any] = {
                "state": "todo",
                "scope": "personal",
                "list_id": {"$exists": False},
            }
            query["user_id"] = user_id
        else:
            query = {
                "state": "todo",
                "guild_id": guild_id,
                "scope": {"$ne": "personal"},
                "list_id": {"$exists": False},
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
                {"$set": {"state": "done", "status": "done"}},
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
            {"$set": {"state": "done", "status": "done"}},
        )

        return result.modified_count > 0

    @staticmethod
    def create_todo_list(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        name: str,
        scope: str = "channel",
    ) -> Dict[str, Any]:
        cleaned_name = TodoFunctions._clean_list_name(name)
        scope_value = TodoFunctions._normalize_scope(scope)

        if scope_value == "channel" and guild_id is None:
            raise ValueError("Channel lists can only be created in servers.")

        stored_guild_id = None if scope_value == "personal" else guild_id
        stored_channel_id = None if scope_value == "personal" else channel_id
        query = TodoFunctions._build_list_query(
            stored_guild_id,
            user_id,
            stored_channel_id,
            cleaned_name,
            scope_value,
        )

        existing = mongo_db["todo_lists"].find_one(query)
        if existing:
            raise ValueError("A list with that name already exists in this scope.")

        document: Dict[str, Any] = {
            "name": cleaned_name,
            "name_key": cleaned_name.lower(),
            "scope": scope_value,
            "guild_id": stored_guild_id,
            "channel_id": stored_channel_id,
            "user_id": user_id,
            "created_at": datetime.datetime.utcnow().isoformat(),
        }

        result = mongo_db["todo_lists"].insert_one(document)
        document["_id"] = result.inserted_id
        return document

    @staticmethod
    def fetch_todo_list(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        name: str,
        scope: str = "channel",
    ) -> Optional[Dict[str, Any]]:
        cleaned_name = TodoFunctions._clean_list_name(name)
        scope_value = TodoFunctions._normalize_scope(scope)
        stored_guild_id = None if scope_value == "personal" else guild_id
        stored_channel_id = None if scope_value == "personal" else channel_id
        query = TodoFunctions._build_list_query(
            stored_guild_id,
            user_id,
            stored_channel_id,
            cleaned_name,
            scope_value,
        )
        return mongo_db["todo_lists"].find_one(query)

    @staticmethod
    def fetch_todo_list_by_id(list_id: Any) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return None
        return mongo_db["todo_lists"].find_one({"_id": object_id})

    @staticmethod
    def list_candidate_lists_for_item_scope(
        item: Dict[str, Any],
        acting_user_id: int,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        scope_value = TodoFunctions._normalize_scope(str(item.get("scope") or "channel"))
        if scope_value == "personal":
            owner_id = int(item.get("user_id") or acting_user_id)
            query: Dict[str, Any] = {
                "scope": "personal",
                "user_id": owner_id,
            }
        else:
            guild_id = item.get("guild_id")
            if guild_id is None:
                return []
            query = {
                "scope": "channel",
                "guild_id": guild_id,
            }

        capped_limit = max(1, min(limit, 25))
        cursor = (
            mongo_db["todo_lists"]
            .find(query, {"name": 1, "channel_id": 1, "scope": 1})
            .sort("name", 1)
            .limit(capped_limit)
        )
        return list(cursor)

    @staticmethod
    def find_list_for_item_scope(
        item: Dict[str, Any],
        list_name: str,
        acting_user_id: int,
    ) -> Dict[str, Any]:
        cleaned_name = TodoFunctions._clean_list_name(list_name)
        name_key = cleaned_name.lower()
        scope_value = TodoFunctions._normalize_scope(str(item.get("scope") or "channel"))

        if scope_value == "personal":
            owner_id = int(item.get("user_id") or acting_user_id)
            query: Dict[str, Any] = {
                "scope": "personal",
                "user_id": owner_id,
                "name_key": name_key,
            }
        else:
            guild_id = item.get("guild_id")
            if guild_id is None:
                raise ValueError("This item is not attached to a server list.")
            query = {
                "scope": "channel",
                "guild_id": guild_id,
                "name_key": name_key,
            }

        target_list = mongo_db["todo_lists"].find_one(query)
        if not target_list:
            raise ValueError(f"List `{cleaned_name}` was not found for this item scope.")
        return target_list

    @staticmethod
    def find_list_for_item_scope_by_token(
        item: Dict[str, Any],
        list_token: str,
        acting_user_id: int,
    ) -> Dict[str, Any]:
        token = (list_token or "").strip()
        if not token:
            raise ValueError("List value cannot be empty.")

        by_id = TodoFunctions.fetch_todo_list_by_id(token)
        if by_id is not None:
            item_scope = TodoFunctions._normalize_scope(str(item.get("scope") or "channel"))
            list_scope = TodoFunctions._normalize_scope(str(by_id.get("scope") or "channel"))
            if item_scope != list_scope:
                raise ValueError("That list does not match this item scope.")
            if item_scope == "channel":
                if by_id.get("guild_id") != item.get("guild_id"):
                    raise ValueError("That list is not in this server.")
            else:
                owner_id = int(item.get("user_id") or acting_user_id)
                if int(by_id.get("user_id") or 0) != owner_id:
                    raise ValueError("That list is not available for this personal item.")
            return by_id

        return TodoFunctions.find_list_for_item_scope(item, token, acting_user_id)

    @staticmethod
    def move_item_to_list(
        item_id: Any,
        target_list: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        target_list_id = TodoFunctions._coerce_object_id(target_list.get("_id"))
        if object_id is None or target_list_id is None:
            return None

        current_item = mongo_db["todos"].find_one({"_id": object_id}, {"list_id": 1})
        if not current_item:
            return None

        existing_list_id = TodoFunctions._coerce_object_id(current_item.get("list_id"))
        if existing_list_id == target_list_id:
            return mongo_db["todos"].find_one({"_id": object_id})

        next_item_no = TodoFunctions._next_item_number(target_list_id)
        target_scope = TodoFunctions._normalize_scope(str(target_list.get("scope") or "channel"))

        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "list_id": target_list_id,
                    "item_no": next_item_no,
                    "scope": target_scope,
                    "guild_id": target_list.get("guild_id"),
                    "channel_id": target_list.get("channel_id"),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return updated

    @staticmethod
    def delete_todo_list(list_id: Any) -> Tuple[bool, int]:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return False, 0

        list_delete = mongo_db["todo_lists"].delete_one({"_id": object_id})
        item_delete = mongo_db["todos"].delete_many({"list_id": object_id})
        return list_delete.deleted_count > 0, item_delete.deleted_count

    @staticmethod
    def clear_todo_list_items(list_id: Any) -> int:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return 0
        deleted = mongo_db["todos"].delete_many({"list_id": object_id})
        return deleted.deleted_count

    @staticmethod
    def _next_item_number(list_id: ObjectId) -> int:
        latest = (
            mongo_db["todos"]
            .find({"list_id": list_id}, {"item_no": 1})
            .sort("item_no", -1)
            .limit(1)
        )
        latest_doc = next(latest, None)
        if not latest_doc:
            return 1
        return int(latest_doc.get("item_no", 0)) + 1

    @staticmethod
    def add_item_to_list(
        todo_list: Dict[str, Any],
        user_id: int,
        text: str,
        due: Optional[str] = None,
        status: str = "todo",
        assignee_id: Optional[int] = None,
        timezone: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[datetime.datetime]]:
        list_id = TodoFunctions._coerce_object_id(todo_list.get("_id"))
        if list_id is None:
            raise ValueError("That list is invalid.")

        cleaned_text = TodoFunctions._clean_item_text(text)
        due_dt = TodoFunctions._parse_due_datetime(due, timezone=timezone)
        item_no = TodoFunctions._next_item_number(list_id)
        title = TodoFunctions._item_title_from_text(cleaned_text)
        normalized_status = (status or "todo").strip().lower()
        if normalized_status not in TodoFunctions._ALLOWED_ITEM_STATUSES:
            raise ValueError("Invalid status.")
        state_value = "done" if normalized_status == "done" else "todo"
        assignees = [assignee_id] if assignee_id is not None else []

        document: Dict[str, Any] = {
            "guild_id": todo_list.get("guild_id"),
            "channel_id": todo_list.get("channel_id"),
            "user_id": user_id,
            "scope": todo_list.get("scope", "channel"),
            "state": state_value,
            "status": normalized_status,
            "list_id": list_id,
            "item_no": item_no,
            "name": title,
            "description": cleaned_text,
            "text": cleaned_text,
            "assignees": assignees,
            "due": due_dt.isoformat() if due_dt else None,
        }
        result = mongo_db["todos"].insert_one(document)
        document["_id"] = result.inserted_id
        return document, due_dt

    @staticmethod
    def list_items_on_list(
        list_id: Any,
        sort: str = "ascending",
    ) -> List[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return []

        sort_direction = 1 if sort == "ascending" else -1
        cursor = mongo_db["todos"].find({"list_id": object_id}).sort(
            "item_no", sort_direction
        )
        return list(cursor)

    @staticmethod
    def list_items_on_guild(
        guild_id: Optional[int],
        sort: str = "ascending",
    ) -> List[Dict[str, Any]]:
        if guild_id is None:
            return []

        sort_direction = 1 if sort == "ascending" else -1
        list_docs = mongo_db["todo_lists"].find(
            {"guild_id": guild_id, "scope": "channel"},
            {"_id": 1, "name": 1},
        )
        list_name_map: Dict[ObjectId, str] = {
            doc["_id"]: str(doc.get("name") or "Unnamed")
            for doc in list_docs
            if isinstance(doc.get("_id"), ObjectId)
        }

        cursor = mongo_db["todos"].find(
            {
                "guild_id": guild_id,
                "scope": {"$ne": "personal"},
                "list_id": {"$exists": True},
            }
        ).sort("_id", sort_direction)
        items = list(cursor)

        for item in items:
            list_id = item.get("list_id")
            if isinstance(list_id, ObjectId):
                item["list_name"] = list_name_map.get(list_id, "Unnamed")

        return items

    @staticmethod
    def fetch_item_on_list(
        list_id: Any,
        item_no: int,
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return None
        return mongo_db["todos"].find_one({"list_id": object_id, "item_no": item_no})

    @staticmethod
    def set_item_text(
        item_id: Any,
        text: str,
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return None

        cleaned_text = TodoFunctions._clean_item_text(text)
        title = TodoFunctions._item_title_from_text(cleaned_text)

        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "name": title,
                    "description": cleaned_text,
                    "text": cleaned_text,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return updated

    @staticmethod
    def set_item_fields(
        item_id: Any,
        task_text: str,
        description: Optional[str],
        status: str,
        due: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return None

        title = TodoFunctions._clean_item_title(task_text)
        cleaned_description = TodoFunctions._clean_item_description(description)
        combined_text = (
            f"{title}\n{cleaned_description}"
            if cleaned_description
            else title
        )
        cleaned_text = TodoFunctions._clean_item_text(combined_text)
        normalized_status = TodoFunctions._normalize_item_status(status)
        state_value = "done" if normalized_status == "done" else "todo"
        due_value = TodoFunctions._parse_due_input_value(due)

        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "name": title,
                    "description": cleaned_description,
                    "text": cleaned_text,
                    "status": normalized_status,
                    "state": state_value,
                    "due": due_value,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return updated

    @staticmethod
    def set_item_status(
        item_id: Any,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return None

        normalized = TodoFunctions._normalize_item_status(status)

        state_value = "done" if normalized == "done" else "todo"
        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {"$set": {"status": normalized, "state": state_value}},
            return_document=ReturnDocument.AFTER,
        )
        return updated

    @staticmethod
    def delete_item(
        item_id: Any,
    ) -> bool:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return False
        deleted = mongo_db["todos"].delete_one({"_id": object_id})
        return deleted.deleted_count > 0

    @staticmethod
    def add_assignee(
        item_id: Any,
        user_id: int,
    ) -> bool:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return False

        updated = mongo_db["todos"].update_one(
            {"_id": object_id},
            {"$addToSet": {"assignees": user_id}},
        )
        return updated.modified_count > 0

    @staticmethod
    def remove_assignee(
        item_id: Any,
        user_id: int,
    ) -> bool:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return False

        updated = mongo_db["todos"].update_one(
            {"_id": object_id},
            {"$pull": {"assignees": user_id}},
        )
        return updated.modified_count > 0

    @staticmethod
    def set_item_assignee(
        item_id: Any,
        user_id: Optional[int],
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return None

        assignees: List[int] = [user_id] if user_id is not None else []
        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {"$set": {"assignees": assignees}},
            return_document=ReturnDocument.AFTER,
        )
        return updated
