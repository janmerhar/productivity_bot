import datetime
import re
from typing import Optional, Tuple, Dict, Any, List, Union

from bson.objectid import ObjectId
from pymongo import ReturnDocument

from classes.DailyJob import OneTimeSchedule2
from config.db import mongo_db
from services.due_datetime import DueDateService


def _ensure_todo_indexes() -> None:
    mongo_db["todos"].create_index(
        [("list_id", 1), ("created_at", -1)],
        name="todos_by_list_created_at",
    )
    mongo_db["todos"].create_index(
        [("list_id", 1), ("title_key", 1), ("created_at", -1)],
        name="todos_autocomplete_title",
    )

    mongo_db["todo_lists"].create_index(
        [("scope", 1), ("user_id", 1), ("name_key", 1)],
        unique=True,
        partialFilterExpression={"scope": "personal"},
        name="todo_lists_personal_name_unique",
    )
    mongo_db["todo_lists"].create_index(
        [("scope", 1), ("guild_id", 1), ("channel_id", 1), ("name_key", 1)],
        unique=True,
        partialFilterExpression={"scope": "channel"},
        name="todo_lists_channel_name_unique",
    )

    mongo_db["todo_lists"].create_index(
        [("scope", 1), ("user_id", 1), ("name", 1)],
        partialFilterExpression={"scope": "personal"},
        name="todo_lists_personal_browse",
    )
    mongo_db["todo_lists"].create_index(
        [("scope", 1), ("guild_id", 1), ("name", 1)],
        partialFilterExpression={"scope": "channel"},
        name="todo_lists_channel_browse",
    )


_ensure_todo_indexes()


class TodoFunctions:
    _MAX_LIST_NAME_LEN = 80
    _MAX_ITEM_TEXT_LEN = 800
    _MAX_TITLE_LEN = 100
    _ALLOWED_ITEM_STATUSES = {"todo", "in_progress", "done"}
    _DEFAULT_LIST_TYPE = "default"
    _CUSTOM_LIST_TYPE = "custom"
    _SERVER_INBOX_DISPLAY_NAME = "Server Todos"
    _SERVER_INBOX_LEGACY_NAME = "Inbox"
    _TODO_REMINDER_DELIVERIES = {"auto", "channel", "dm_me", "dm_assignee", "off"}

    @staticmethod
    def normalize_todo_reminder_delivery(value: Any) -> str:
        normalized = str(value or "auto").strip().lower()
        if normalized not in TodoFunctions._TODO_REMINDER_DELIVERIES:
            return "auto"
        return normalized

    @staticmethod
    def _normalize_scope(scope: str) -> str:
        return scope if scope in ("channel", "personal") else "channel"

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
    def list_type(todo_list: Optional[Dict[str, Any]]) -> str:
        if not todo_list:
            return TodoFunctions._CUSTOM_LIST_TYPE

        explicit = str(todo_list.get("list_type") or "").strip().lower()
        if explicit in {
            TodoFunctions._DEFAULT_LIST_TYPE,
            TodoFunctions._CUSTOM_LIST_TYPE,
        }:
            return explicit
        return TodoFunctions._CUSTOM_LIST_TYPE

    @staticmethod
    def is_server_inbox_list(todo_list: Optional[Dict[str, Any]]) -> bool:
        if not todo_list:
            return False
        return (
            TodoFunctions._normalize_scope(str(todo_list.get("scope") or "")) == "channel"
            and todo_list.get("guild_id") is not None
            and todo_list.get("channel_id") is None
            and TodoFunctions.list_type(todo_list) == TodoFunctions._DEFAULT_LIST_TYPE
        )

    @staticmethod
    def display_list_name(
        todo_list: Optional[Dict[str, Any]],
        fallback: str = "List",
    ) -> str:
        if TodoFunctions.is_server_inbox_list(todo_list):
            return TodoFunctions._SERVER_INBOX_DISPLAY_NAME
        return str((todo_list or {}).get("name") or fallback)

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
            raise ValueError("Invalid status. Use one of: todo, in_progress, done.")
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
    def _item_title_key(value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def _item_autocomplete_search_text(item: Dict[str, Any]) -> str:
        list_name = str(item.get("list_name") or "List").strip() or "List"
        todo_name = TodoFunctions.task_name_from_item(item) or "Untitled"
        status = TodoFunctions.status_label(TodoFunctions.item_status(item))
        due_value = TodoFunctions.item_due(item)
        due_label = DueDateService.format_due(due_value) if due_value else "No due date"
        return TodoFunctions._item_title_key(
            f"{list_name} {todo_name} {status} {due_label}"
        )

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
    def task_name_from_item(item: Dict[str, Any]) -> str:
        return str(item["title"]).strip()

    @staticmethod
    def item_body(item: Dict[str, Any]) -> str:
        return str(item.get("body") or "").strip()

    @staticmethod
    def item_due(
        item: Dict[str, Any]
    ) -> Optional[Union[datetime.datetime, str]]:
        return TodoFunctions._coerce_utc_datetime(item.get("due_at"))

    @staticmethod
    def item_assignee_id(item: Dict[str, Any]) -> Optional[int]:
        value = item.get("assignee_id")
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def item_assignee_ids(item: Dict[str, Any]) -> List[int]:
        assignee_id = TodoFunctions.item_assignee_id(item)
        return [assignee_id] if assignee_id is not None else []

    @staticmethod
    def _split_item_text(text: str) -> Tuple[str, Optional[str]]:
        cleaned_text = TodoFunctions._clean_item_text(text)
        title = TodoFunctions._item_title_from_text(cleaned_text)
        body = "\n".join(cleaned_text.splitlines()[1:]).strip()
        return title, body or None

    @staticmethod
    def _utc_now() -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc)

    @staticmethod
    def _coerce_utc_datetime(
        value: Any,
    ) -> Optional[Union[datetime.datetime, str]]:
        if value is None:
            return None
        if isinstance(value, datetime.datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                return value.replace(tzinfo=datetime.timezone.utc)
            return value.astimezone(datetime.timezone.utc)

        parsed = DueDateService.coerce_due_datetime(value)
        if parsed is None:
            raw = str(value).strip()
            return raw or None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)

    @staticmethod
    def _storage_datetime(value: Any) -> Optional[datetime.datetime]:
        if value is None:
            return None

        parsed: Optional[datetime.datetime]
        if isinstance(value, datetime.datetime):
            parsed = value
        else:
            parsed = DueDateService.coerce_due_datetime(value)
        if parsed is None:
            return None

        if parsed.tzinfo is None or parsed.utcoffset() is None:
            local_tz = datetime.datetime.now().astimezone().tzinfo
            parsed = parsed.replace(tzinfo=local_tz or datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)

    @staticmethod
    def _item_with_list_context(
        item: Optional[Dict[str, Any]],
        todo_list: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if item is None:
            return None

        enriched = dict(item)
        if todo_list is not None:
            enriched["scope"] = str(todo_list.get("scope") or "channel")
            enriched["guild_id"] = todo_list.get("guild_id")
            enriched["channel_id"] = todo_list.get("channel_id")
            enriched["user_id"] = todo_list.get("user_id")
            enriched["list_name"] = TodoFunctions.display_list_name(todo_list, "Unnamed")
        return enriched

    @staticmethod
    def _listless_item_with_context(
        item: Optional[Dict[str, Any]],
        *,
        list_name: str = _SERVER_INBOX_DISPLAY_NAME,
    ) -> Optional[Dict[str, Any]]:
        if item is None:
            return None

        enriched = dict(item)
        enriched["scope"] = TodoFunctions._normalize_scope(
            str(enriched.get("scope") or "channel")
        )
        enriched["list_name"] = list_name
        return enriched

    @staticmethod
    def _list_map_by_id(
        list_docs: List[Dict[str, Any]],
    ) -> Dict[ObjectId, Dict[str, Any]]:
        return {
            doc["_id"]: doc
            for doc in list_docs
            if isinstance(doc.get("_id"), ObjectId)
        }

    @staticmethod
    def _items_scope_query(
        guild_id: Optional[int],
        user_id: int,
        list_ids: List[ObjectId],
    ) -> Dict[str, Any]:
        list_clauses: List[Dict[str, Any]] = []
        if list_ids:
            list_clauses.append({"list_id": {"$in": list_ids}})

        if guild_id is not None:
            list_clauses.append({"guild_id": guild_id, "list_id": None})
        else:
            list_clauses.append(
                {
                    "list_id": None,
                    "$or": [
                        {"scope": "personal", "user_id": user_id},
                        {"guild_id": None, "user_id": user_id},
                        {"guild_id": None, "created_by_user_id": user_id},
                    ],
                }
            )

        if len(list_clauses) == 1:
            return list_clauses[0]
        return {"$or": list_clauses}

    @staticmethod
    def _scope_context_from_item(
        item: Dict[str, Any],
        acting_user_id: int,
    ) -> Dict[str, Any]:
        scope = str(item.get("scope") or "").strip().lower()
        guild_id = item.get("guild_id")
        channel_id = item.get("channel_id")
        owner_user_id = item.get("user_id")

        if scope and (guild_id is not None or owner_user_id is not None):
            return {
                "scope": TodoFunctions._normalize_scope(scope),
                "guild_id": guild_id,
                "channel_id": channel_id,
                "user_id": owner_user_id or acting_user_id,
            }

        list_id = TodoFunctions._coerce_object_id(item.get("list_id"))
        todo_list = (
            mongo_db["todo_lists"].find_one({"_id": list_id}) if list_id is not None else None
        )
        if todo_list is not None:
            return {
                "scope": TodoFunctions._normalize_scope(
                    str(todo_list.get("scope") or "channel")
                ),
                "guild_id": todo_list.get("guild_id"),
                "channel_id": todo_list.get("channel_id"),
                "user_id": todo_list.get("user_id") or acting_user_id,
            }

        return {
            "scope": "channel",
            "guild_id": guild_id,
            "channel_id": channel_id,
            "user_id": owner_user_id or acting_user_id,
        }

    @staticmethod
    def task_ref(task_name: str, limit: int = 80) -> str:
        sanitized = str(task_name).strip().replace("`", "'")
        if len(sanitized) > limit:
            sanitized = sanitized[: max(0, limit - 3)].rstrip() + "..."
        return f"`{sanitized}`"

    @staticmethod
    def task_ref_from_item(item: Dict[str, Any], limit: int = 80) -> str:
        return TodoFunctions.task_ref(
            TodoFunctions.task_name_from_item(item),
            limit=limit,
        )

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
            TodoFunctions.trim_text(
                normalized_content, TodoFunctions._MAX_ITEM_TEXT_LEN
            )
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
    def _implicit_list_name(
        channel_name: Optional[str],
        channel_id: Optional[int],
    ) -> str:
        cleaned_name = (channel_name or "").strip()
        if cleaned_name:
            return TodoFunctions.trim_text(
                cleaned_name, TodoFunctions._MAX_LIST_NAME_LEN
            )
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
            "name_key": name_key,
        }
        existing = mongo_db["todo_lists"].find_one(query)
        if existing:
            updates: Dict[str, Any] = {}
            if existing.get("name") != list_name:
                updates["name"] = list_name
            if existing.get("name_key") != name_key:
                updates["name_key"] = name_key
            if existing.get("list_type") != TodoFunctions._DEFAULT_LIST_TYPE:
                updates["list_type"] = TodoFunctions._DEFAULT_LIST_TYPE
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
            "list_type": TodoFunctions._DEFAULT_LIST_TYPE,
            "created_at": TodoFunctions._utc_now(),
        }

        result = mongo_db["todo_lists"].insert_one(document)
        document["_id"] = result.inserted_id
        return document

    @staticmethod
    def get_or_create_server_global_list(
        guild_id: Optional[int],
        user_id: int,
    ) -> Dict[str, Any]:
        if guild_id is None:
            raise ValueError("Server-global lists are only available in servers.")

        list_name = TodoFunctions._SERVER_INBOX_DISPLAY_NAME
        query: Dict[str, Any] = {
            "scope": "channel",
            "guild_id": guild_id,
            "channel_id": None,
            "list_type": TodoFunctions._DEFAULT_LIST_TYPE,
        }
        existing = mongo_db["todo_lists"].find_one(query)
        if not existing:
            existing = mongo_db["todo_lists"].find_one(
                {
                    "scope": "channel",
                    "guild_id": guild_id,
                    "channel_id": None,
                    "name_key": {
                        "$in": [
                            list_name.lower(),
                            TodoFunctions._SERVER_INBOX_LEGACY_NAME.lower(),
                        ]
                    },
                    "list_type": {"$ne": TodoFunctions._CUSTOM_LIST_TYPE},
                }
            )
        if existing:
            updates: Dict[str, Any] = {}
            if existing.get("name") != list_name:
                updates["name"] = list_name
            if existing.get("name_key") != list_name.lower():
                updates["name_key"] = list_name.lower()
            if existing.get("list_type") != TodoFunctions._DEFAULT_LIST_TYPE:
                updates["list_type"] = TodoFunctions._DEFAULT_LIST_TYPE
            if updates:
                mongo_db["todo_lists"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": updates},
                )
                existing.update(updates)
            return existing

        document: Dict[str, Any] = {
            "name": list_name,
            "name_key": list_name.lower(),
            "scope": "channel",
            "guild_id": guild_id,
            "channel_id": None,
            "user_id": user_id,
            "list_type": TodoFunctions._DEFAULT_LIST_TYPE,
            "created_at": TodoFunctions._utc_now(),
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
            "name_key": "personal",
        }
        existing = mongo_db["todo_lists"].find_one(query)
        if existing:
            updates: Dict[str, Any] = {}
            if existing.get("name") != "Personal":
                updates["name"] = "Personal"
            if existing.get("name_key") != "personal":
                updates["name_key"] = "personal"
            if existing.get("list_type") != TodoFunctions._DEFAULT_LIST_TYPE:
                updates["list_type"] = TodoFunctions._DEFAULT_LIST_TYPE
            if updates:
                mongo_db["todo_lists"].update_one(
                    {"_id": existing["_id"]},
                    {"$set": updates},
                )
                existing.update(updates)
            return existing

        document: Dict[str, Any] = {
            "name": "Personal",
            "name_key": "personal",
            "scope": "personal",
            "guild_id": None,
            "channel_id": None,
            "user_id": user_id,
            "list_type": TodoFunctions._DEFAULT_LIST_TYPE,
            "created_at": TodoFunctions._utc_now(),
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
                raise ValueError(
                    "Please select an assignee from autocomplete options."
                ) from exc
        raise ValueError("Please select an assignee from autocomplete options.")

    @staticmethod
    def item_text(item: Dict[str, Any]) -> str:
        body = TodoFunctions.item_body(item)
        if body:
            return body
        return TodoFunctions.task_name_from_item(item)

    @staticmethod
    def item_status(item: Dict[str, Any]) -> str:
        status = str(item.get("status") or "").strip().lower()
        if status in TodoFunctions._ALLOWED_ITEM_STATUSES:
            return status
        return "todo"

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
        reminder_delivery: str = "auto",
        reminder_channel_id: Optional[int] = None,
    ) -> None:
        from classes.DailyJobManager import DailyJobManager

        delivery = TodoFunctions.normalize_todo_reminder_delivery(reminder_delivery)
        if delivery == "off":
            return

        schedule = OneTimeSchedule2(datetime=due_dt.isoformat())
        task_id = str(todo.get("_id"))
        todo_list = TodoFunctions.fetch_todo_list_by_id(todo.get("list_id"))
        guild_id = None if todo_list is None else todo_list.get("guild_id")
        channel_id = None
        if delivery == "channel" or (
            delivery == "auto"
            and TodoFunctions._normalize_scope(str(todo.get("scope") or "")) == "channel"
        ):
            channel_id = reminder_channel_id
            if channel_id is None and todo_list is not None:
                channel_id = todo_list.get("channel_id")

        data: Dict[str, Any] = {
            "task_id": task_id,
            "reminder_delivery": delivery,
        }
        created_by_user_id = todo.get("created_by_user_id") or todo.get("user_id")
        assignee_id = TodoFunctions.item_assignee_id(todo)
        if created_by_user_id is not None:
            data["created_by_user_id"] = created_by_user_id
        if assignee_id is not None:
            data["assignee_id"] = assignee_id
        if reminder_channel_id is not None:
            data["source_channel_id"] = reminder_channel_id

        manager = DailyJobManager()
        manager.insert_job(
            guild_id=guild_id,
            channel_id=channel_id,
            type="todo",
            data=data,
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

        item_text = cleaned_name
        cleaned_description = description.strip() if description else None
        if cleaned_description:
            item_text = f"{cleaned_name}\n{cleaned_description}"

        todo_list = TodoFunctions.get_or_create_implicit_list(
            guild_id,
            channel_id,
            user_id,
            None,
            scope,
        )
        return TodoFunctions.add_item_to_list(
            todo_list,
            user_id,
            item_text,
            due,
            "todo",
            None,
        )

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
            items = TodoFunctions.list_items_on_personal_scope(user_id, sort)
        else:
            items = TodoFunctions.list_items_on_guild(guild_id, sort)
            if mode != "all":
                items = [
                    item for item in items if item.get("channel_id") == channel_id
                ]

        return [
            item for item in items if TodoFunctions.item_status(item) != "done"
        ]

    @staticmethod
    def fetch_todo(
        todo_id: str, guild_id: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return None

        todo = mongo_db["todos"].find_one({"_id": object_id})
        if todo is None:
            return None

        todo_list = TodoFunctions.fetch_todo_list_by_id(todo.get("list_id"))
        if guild_id is not None:
            if todo_list is None:
                if todo.get("guild_id") != guild_id:
                    return None
                return TodoFunctions._listless_item_with_context(todo)
            if TodoFunctions._normalize_scope(str(todo_list.get("scope") or "")) != "channel":
                return None
            if todo_list.get("guild_id") != guild_id:
                return None

        return TodoFunctions._item_with_list_context(todo, todo_list)

    @staticmethod
    def fetch_todo_for_scope(
        todo_id: str,
        guild_id: Optional[int],
        user_id: int,
    ) -> Optional[Dict[str, Any]]:
        try:
            object_id = ObjectId(todo_id)
        except Exception:
            return None

        todo = mongo_db["todos"].find_one({"_id": object_id})
        if todo is None:
            return None

        todo_list = TodoFunctions.fetch_todo_list_by_id(todo.get("list_id"))
        if todo_list is None:
            if guild_id is None:
                owner_id = int(todo.get("user_id") or todo.get("created_by_user_id") or 0)
                if owner_id != user_id:
                    return None
                return TodoFunctions._listless_item_with_context(
                    todo,
                    list_name="Personal",
                )

            if todo.get("guild_id") != guild_id:
                return None
            return TodoFunctions._listless_item_with_context(todo)

        scope_value = TodoFunctions._normalize_scope(str(todo_list.get("scope") or "channel"))
        if guild_id is None:
            if scope_value != "personal" or int(todo_list.get("user_id") or 0) != user_id:
                return None
        else:
            if scope_value != "channel" or todo_list.get("guild_id") != guild_id:
                return None

        return TodoFunctions._item_with_list_context(todo, todo_list)

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
        todo = mongo_db["todos"].find_one({"_id": object_id})
        if todo is None:
            return False

        todo_list = TodoFunctions.fetch_todo_list_by_id(todo.get("list_id"))
        if todo_list is None:
            return False

        scope_value = TodoFunctions._normalize_scope(str(todo_list.get("scope") or "channel"))
        if scope_value == "personal":
            if user_id is None or int(todo_list.get("user_id") or 0) != user_id:
                return False
        else:
            if guild_id is None or todo_list.get("guild_id") != guild_id:
                return False

        now_dt = TodoFunctions._utc_now()
        result = mongo_db["todos"].update_one(
            {"_id": object_id},
            {
                "$set": {
                    "status": "done",
                    "completed_at": now_dt,
                    "updated_at": now_dt,
                }
            },
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
            raise ValueError("Server lists can only be created in servers.")

        stored_guild_id = None if scope_value == "personal" else guild_id
        stored_channel_id = None
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
            "list_type": TodoFunctions._CUSTOM_LIST_TYPE,
            "created_at": TodoFunctions._utc_now(),
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
    def list_custom_lists_for_context(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        capped_limit = max(1, min(limit, 100))
        queries: List[Dict[str, Any]] = [
            {
                "scope": "personal",
                "user_id": user_id,
                "list_type": TodoFunctions._CUSTOM_LIST_TYPE,
            }
        ]
        if guild_id is not None:
            queries.append(
                {
                    "scope": "channel",
                    "guild_id": guild_id,
                    "channel_id": None,
                    "list_type": TodoFunctions._CUSTOM_LIST_TYPE,
                }
            )

        query: Dict[str, Any]
        if len(queries) == 1:
            query = queries[0]
        else:
            query = {"$or": queries}

        cursor = (
            mongo_db["todo_lists"]
            .find(query, {"name": 1, "scope": 1, "channel_id": 1, "list_type": 1})
            .sort([("scope", 1), ("name", 1)])
            .limit(capped_limit)
        )
        return list(cursor)

    @staticmethod
    def list_custom_lists_for_scope(
        guild_id: Optional[int],
        user_id: int,
        channel_id: Optional[int],
        scope: str,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        scope_value = TodoFunctions._normalize_scope(scope)
        capped_limit = max(1, min(limit, 100))
        if scope_value == "personal":
            query: Dict[str, Any] = {
                "scope": "personal",
                "user_id": user_id,
                "list_type": TodoFunctions._CUSTOM_LIST_TYPE,
            }
        else:
            query = {
                "scope": "channel",
                "guild_id": guild_id,
                "channel_id": None,
                "list_type": TodoFunctions._CUSTOM_LIST_TYPE,
            }

        cursor = (
            mongo_db["todo_lists"]
            .find(query, {"name": 1, "scope": 1, "channel_id": 1, "list_type": 1})
            .sort("name", 1)
            .limit(capped_limit)
        )
        return list(cursor)

    @staticmethod
    def rename_todo_list(
        list_id: Any,
        new_name: str,
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return None

        current = mongo_db["todo_lists"].find_one({"_id": object_id})
        if not current:
            return None
        if TodoFunctions.list_type(current) != TodoFunctions._CUSTOM_LIST_TYPE:
            raise ValueError("Only custom lists can be renamed.")

        cleaned_name = TodoFunctions._clean_list_name(new_name)
        duplicate_query = TodoFunctions._build_list_query(
            current.get("guild_id"),
            int(current.get("user_id") or 0),
            current.get("channel_id"),
            cleaned_name,
            str(current.get("scope") or "channel"),
        )
        duplicate = mongo_db["todo_lists"].find_one(duplicate_query)
        if duplicate and duplicate.get("_id") != object_id:
            raise ValueError("A list with that name already exists in this scope.")

        updated = mongo_db["todo_lists"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "name": cleaned_name,
                    "name_key": cleaned_name.lower(),
                    "list_type": TodoFunctions._CUSTOM_LIST_TYPE,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return updated

    @staticmethod
    def list_candidate_lists_for_item_scope(
        item: Dict[str, Any],
        acting_user_id: int,
        limit: int = 25,
    ) -> List[Dict[str, Any]]:
        context = TodoFunctions._scope_context_from_item(item, acting_user_id)
        scope_value = context["scope"]
        if scope_value == "personal":
            owner_id = int(context.get("user_id") or acting_user_id)
            query: Dict[str, Any] = {
                "scope": "personal",
                "user_id": owner_id,
            }
        else:
            guild_id = context.get("guild_id")
            if guild_id is None:
                return []
            query = {
                "scope": "channel",
                "guild_id": guild_id,
            }

        capped_limit = max(1, min(limit, 25))
        cursor = (
            mongo_db["todo_lists"]
            .find(query, {"name": 1, "channel_id": 1, "scope": 1, "list_type": 1, "guild_id": 1})
            .sort("name", 1)
            .limit(capped_limit + 1)
        )
        return list(cursor)[:capped_limit]

    @staticmethod
    def find_list_for_item_scope(
        item: Dict[str, Any],
        list_name: str,
        acting_user_id: int,
    ) -> Dict[str, Any]:
        cleaned_name = TodoFunctions._clean_list_name(list_name)
        name_key = cleaned_name.lower()
        context = TodoFunctions._scope_context_from_item(item, acting_user_id)
        scope_value = context["scope"]

        if scope_value == "personal":
            owner_id = int(context.get("user_id") or acting_user_id)
            query: Dict[str, Any] = {
                "scope": "personal",
                "user_id": owner_id,
                "name_key": name_key,
            }
        else:
            guild_id = context.get("guild_id")
            if guild_id is None:
                raise ValueError("This item is not attached to a server list.")
            query = {
                "scope": "channel",
                "guild_id": guild_id,
                "name_key": name_key,
            }

        target_list = mongo_db["todo_lists"].find_one(query)
        if not target_list:
            raise ValueError(
                f"List `{cleaned_name}` was not found for this item scope."
            )
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

        token_lower = token.lower()
        if token_lower == "__personal__":
            return TodoFunctions.get_or_create_implicit_list(
                guild_id=None,
                channel_id=None,
                user_id=acting_user_id,
                channel_name=None,
                target="personal",
            )
        if token_lower == "__server_inbox__":
            context = TodoFunctions._scope_context_from_item(item, acting_user_id)
            return TodoFunctions.get_or_create_server_global_list(
                guild_id=context.get("guild_id"),
                user_id=acting_user_id,
            )

        by_id = TodoFunctions.fetch_todo_list_by_id(token)
        if by_id is not None:
            context = TodoFunctions._scope_context_from_item(item, acting_user_id)
            item_scope = context["scope"]
            list_scope = TodoFunctions._normalize_scope(
                str(by_id.get("scope") or "channel")
            )
            if item_scope != list_scope:
                raise ValueError("That list does not match this item scope.")
            if item_scope == "channel":
                if by_id.get("guild_id") != context.get("guild_id"):
                    raise ValueError("That list is not in this server.")
            else:
                owner_id = int(context.get("user_id") or acting_user_id)
                if int(by_id.get("user_id") or 0) != owner_id:
                    raise ValueError(
                        "That list is not available for this personal item."
                    )
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
            existing_item = mongo_db["todos"].find_one({"_id": object_id})
            return TodoFunctions._item_with_list_context(existing_item, target_list)

        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "list_id": target_list_id,
                    "updated_at": TodoFunctions._utc_now(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return TodoFunctions._item_with_list_context(updated, target_list)

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
    def clear_items_on_guild(guild_id: Optional[int]) -> int:
        if guild_id is None:
            return 0

        list_ids = [
            doc["_id"]
            for doc in mongo_db["todo_lists"].find(
                {"guild_id": guild_id, "scope": "channel"},
                {"_id": 1},
            )
            if isinstance(doc.get("_id"), ObjectId)
        ]
        if not list_ids:
            return 0
        deleted = mongo_db["todos"].delete_many({"list_id": {"$in": list_ids}})
        return deleted.deleted_count

    @staticmethod
    def count_items_on_guild(guild_id: Optional[int]) -> int:
        if guild_id is None:
            return 0
        list_ids = [
            doc["_id"]
            for doc in mongo_db["todo_lists"].find(
                {"guild_id": guild_id, "scope": "channel"},
                {"_id": 1},
            )
            if isinstance(doc.get("_id"), ObjectId)
        ]
        if not list_ids:
            return 0
        return mongo_db["todos"].count_documents({"list_id": {"$in": list_ids}})

    @staticmethod
    def count_items_on_list(list_id: Any) -> int:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return 0
        return mongo_db["todos"].count_documents({"list_id": object_id})

    @staticmethod
    def count_items_for_lists(list_ids: List[Any]) -> Dict[str, int]:
        object_ids: List[ObjectId] = []
        seen_ids: set[ObjectId] = set()
        for value in list_ids:
            object_id = TodoFunctions._coerce_object_id(value)
            if object_id is None or object_id in seen_ids:
                continue
            object_ids.append(object_id)
            seen_ids.add(object_id)

        if not object_ids:
            return {}

        pipeline = [
            {"$match": {"list_id": {"$in": object_ids}}},
            {"$group": {"_id": "$list_id", "count": {"$sum": 1}}},
        ]
        counts: Dict[str, int] = {}
        for row in mongo_db["todos"].aggregate(pipeline):
            list_id = row.get("_id")
            if list_id is None:
                continue
            counts[str(list_id)] = int(row.get("count") or 0)
        return counts

    @staticmethod
    def add_item_to_list(
        todo_list: Dict[str, Any],
        user_id: int,
        text: str,
        due: Optional[str] = None,
        status: str = "todo",
        assignee_id: Optional[int] = None,
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> Tuple[Dict[str, Any], Optional[datetime.datetime]]:
        list_id = TodoFunctions._coerce_object_id(todo_list.get("_id"))
        if list_id is None:
            raise ValueError("That list is invalid.")

        cleaned_text = TodoFunctions._clean_item_text(text)
        due_dt = DueDateService.parse_due_datetime(
            due,
            timezone=timezone,
            locale_code=locale_code,
        )
        title, body = TodoFunctions._split_item_text(cleaned_text)
        normalized_status = (status or "todo").strip().lower()
        if normalized_status not in TodoFunctions._ALLOWED_ITEM_STATUSES:
            raise ValueError("Invalid status.")
        now_dt = TodoFunctions._utc_now()

        document: Dict[str, Any] = {
            "status": normalized_status,
            "list_id": list_id,
            "title": title,
            "title_key": TodoFunctions._item_title_key(title),
            "body": body,
            "assignee_id": assignee_id,
            "created_by_user_id": user_id,
            "due_at": TodoFunctions._storage_datetime(due_dt),
            "completed_at": now_dt if normalized_status == "done" else None,
            "created_at": now_dt,
            "updated_at": now_dt,
        }
        result = mongo_db["todos"].insert_one(document)
        document["_id"] = result.inserted_id
        return TodoFunctions._item_with_list_context(document, todo_list), due_dt

    @staticmethod
    def list_items_on_list(
        list_id: Any,
        sort: str = "ascending",
    ) -> List[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(list_id)
        if object_id is None:
            return []

        todo_list = mongo_db["todo_lists"].find_one({"_id": object_id})
        sort_direction = 1 if sort == "ascending" else -1
        cursor = (
            mongo_db["todos"]
            .find({"list_id": object_id})
            .sort("created_at", sort_direction)
        )
        return [
            TodoFunctions._item_with_list_context(item, todo_list) for item in cursor
        ]

    @staticmethod
    def list_items_on_guild(
        guild_id: Optional[int],
        sort: str = "ascending",
    ) -> List[Dict[str, Any]]:
        if guild_id is None:
            return []

        sort_direction = 1 if sort == "ascending" else -1
        list_docs = list(
            mongo_db["todo_lists"].find(
                {"guild_id": guild_id, "scope": "channel"},
                {"_id": 1, "name": 1, "channel_id": 1, "scope": 1, "list_type": 1, "guild_id": 1, "user_id": 1},
            )
        )
        list_map = TodoFunctions._list_map_by_id(list_docs)
        list_ids = list(list_map)
        item_query = TodoFunctions._items_scope_query(guild_id, 0, list_ids)

        cursor = (
            mongo_db["todos"]
            .find(item_query)
            .sort("created_at", sort_direction)
        )
        items = []
        for item in cursor:
            list_id = item.get("list_id")
            todo_list = list_map.get(list_id) if isinstance(list_id, ObjectId) else None
            if todo_list is None:
                enriched = TodoFunctions._listless_item_with_context(item)
            else:
                enriched = TodoFunctions._item_with_list_context(item, todo_list)
            if enriched is not None:
                items.append(enriched)
        return items

    @staticmethod
    def list_items_on_personal_scope(
        user_id: int,
        sort: str = "ascending",
    ) -> List[Dict[str, Any]]:
        sort_direction = 1 if sort == "ascending" else -1
        list_docs = list(
            mongo_db["todo_lists"].find(
                {"scope": "personal", "user_id": user_id},
                {"_id": 1, "name": 1, "scope": 1, "list_type": 1, "user_id": 1},
            )
        )
        list_map = TodoFunctions._list_map_by_id(list_docs)
        if not list_map:
            return []

        cursor = (
            mongo_db["todos"]
            .find({"list_id": {"$in": list(list_map)}})
            .sort("created_at", sort_direction)
        )
        items = []
        for item in cursor:
            list_id = item.get("list_id")
            todo_list = list_map.get(list_id) if isinstance(list_id, ObjectId) else None
            items.append(TodoFunctions._item_with_list_context(item, todo_list))
        return items

    @staticmethod
    def autocomplete_items_for_scope(
        guild_id: Optional[int],
        user_id: int,
        query: str,
        limit: int = 25,
        candidate_limit: int = 200,
    ) -> List[Dict[str, Any]]:
        resolved_limit = max(1, min(limit, 25))
        resolved_candidate_limit = max(resolved_limit, min(candidate_limit, 500))
        normalized_query = TodoFunctions._item_title_key(query)

        if guild_id is None:
            list_docs = list(
                mongo_db["todo_lists"].find(
                    {"scope": "personal", "user_id": user_id},
                    {"_id": 1, "name": 1, "scope": 1, "list_type": 1, "user_id": 1},
                )
            )
        else:
            list_docs = list(
                mongo_db["todo_lists"].find(
                    {"guild_id": guild_id, "scope": "channel"},
                    {
                        "_id": 1,
                        "name": 1,
                        "channel_id": 1,
                        "scope": 1,
                        "list_type": 1,
                        "guild_id": 1,
                        "user_id": 1,
                    },
                )
            )

        list_map = TodoFunctions._list_map_by_id(list_docs)
        list_ids = list(list_map)

        projection = {
            "list_id": 1,
            "title": 1,
            "body": 1,
            "status": 1,
            "due_at": 1,
            "created_at": 1,
            "guild_id": 1,
            "channel_id": 1,
            "user_id": 1,
            "scope": 1,
            "created_by_user_id": 1,
        }
        matches: List[Dict[str, Any]] = []
        seen_ids: set[ObjectId] = set()

        def append_matches(cursor: Any) -> None:
            for item in cursor:
                item_id = item.get("_id")
                if isinstance(item_id, ObjectId):
                    if item_id in seen_ids:
                        continue
                    seen_ids.add(item_id)

                list_id = item.get("list_id")
                todo_list = list_map.get(list_id) if isinstance(list_id, ObjectId) else None
                if todo_list is None:
                    enriched = TodoFunctions._listless_item_with_context(
                        item,
                        list_name=(
                            "Personal"
                            if guild_id is None
                            else TodoFunctions._SERVER_INBOX_DISPLAY_NAME
                        ),
                    )
                else:
                    enriched = TodoFunctions._item_with_list_context(item, todo_list)
                if enriched is None:
                    continue

                if (
                    normalized_query
                    and normalized_query
                    not in TodoFunctions._item_autocomplete_search_text(enriched)
                ):
                    continue

                matches.append(enriched)
                if len(matches) >= resolved_limit:
                    return

        if normalized_query:
            append_matches(
                mongo_db["todos"]
                .find(
                    {
                        **TodoFunctions._items_scope_query(guild_id, user_id, list_ids),
                        "title_key": {"$regex": f"^{re.escape(normalized_query)}"},
                    },
                    projection,
                )
                .sort("created_at", -1)
                .limit(resolved_limit)
            )

        if len(matches) >= resolved_limit:
            return matches

        append_matches(
            mongo_db["todos"]
            .find(TodoFunctions._items_scope_query(guild_id, user_id, list_ids), projection)
            .sort("created_at", -1)
            .limit(resolved_candidate_limit)
        )

        return matches

    @staticmethod
    def set_item_text(
        item_id: Any,
        text: str,
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return None

        title, body = TodoFunctions._split_item_text(text)

        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "title": title,
                    "title_key": TodoFunctions._item_title_key(title),
                    "body": body,
                    "updated_at": TodoFunctions._utc_now(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return TodoFunctions._item_with_list_context(
            updated,
            TodoFunctions.fetch_todo_list_by_id(updated.get("list_id")) if updated else None,
        )

    @staticmethod
    def set_item_fields(
        item_id: Any,
        task_text: str,
        description: Optional[str],
        status: str,
        due: Optional[str],
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return None

        title = TodoFunctions._clean_item_title(task_text)
        cleaned_description = TodoFunctions._clean_item_description(description)
        normalized_status = TodoFunctions._normalize_item_status(status)
        due_value = DueDateService.parse_due_input_value(
            due,
            timezone=timezone,
            locale_code=locale_code,
        )
        now_dt = TodoFunctions._utc_now()

        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "title": title,
                    "title_key": TodoFunctions._item_title_key(title),
                    "body": cleaned_description,
                    "status": normalized_status,
                    "due_at": TodoFunctions._storage_datetime(due_value),
                    "completed_at": now_dt if normalized_status == "done" else None,
                    "updated_at": now_dt,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return TodoFunctions._item_with_list_context(
            updated,
            TodoFunctions.fetch_todo_list_by_id(updated.get("list_id")) if updated else None,
        )

    @staticmethod
    def set_item_status(
        item_id: Any,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        object_id = TodoFunctions._coerce_object_id(item_id)
        if object_id is None:
            return None

        normalized = TodoFunctions._normalize_item_status(status)
        now_dt = TodoFunctions._utc_now()
        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "status": normalized,
                    "completed_at": now_dt if normalized == "done" else None,
                    "updated_at": now_dt,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return TodoFunctions._item_with_list_context(
            updated,
            TodoFunctions.fetch_todo_list_by_id(updated.get("list_id")) if updated else None,
        )

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
            {
                "$set": {
                    "assignee_id": user_id,
                    "updated_at": TodoFunctions._utc_now(),
                }
            },
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
            {"_id": object_id, "assignee_id": user_id},
            {
                "$set": {
                    "assignee_id": None,
                    "updated_at": TodoFunctions._utc_now(),
                }
            },
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

        updated = mongo_db["todos"].find_one_and_update(
            {"_id": object_id},
            {
                "$set": {
                    "assignee_id": user_id,
                    "updated_at": TodoFunctions._utc_now(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        return TodoFunctions._item_with_list_context(
            updated,
            TodoFunctions.fetch_todo_list_by_id(updated.get("list_id")) if updated else None,
        )
