import datetime
import uuid
from typing import Any, Dict, Optional

from config.db import mongo_db

_COLLECTION = mongo_db["todo_list_directory_sessions"]
_SESSION_TTL = datetime.timedelta(days=7)


def _ensure_indexes() -> None:
    _COLLECTION.create_index(
        [("session_id", 1)],
        unique=True,
        name="todo_list_directory_sessions_session_id",
    )
    _COLLECTION.create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="todo_list_directory_sessions_expires_at_ttl",
    )


_ensure_indexes()


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _expiry() -> datetime.datetime:
    return _now() + _SESSION_TTL


def _state_document(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "current_scope": str(state.get("current_scope") or "server").strip(),
        "guild_id": state.get("guild_id"),
        "channel_id": state.get("channel_id"),
        "channel_name": str(state.get("channel_name") or "").strip() or None,
        "user_id": state.get("user_id"),
        "page": max(1, int(state.get("page") or 1)),
        "page_size": max(1, int(state.get("page_size") or 5)),
        "sort_direction": str(state.get("sort_direction") or "ascending").strip(),
    }


def create_session(state: Dict[str, Any]) -> str:
    document = _state_document(state)
    for _ in range(5):
        session_id = uuid.uuid4().hex[:16]
        payload = dict(document)
        payload.update(
            {
                "session_id": session_id,
                "created_at": _now(),
                "updated_at": _now(),
                "expires_at": _expiry(),
            }
        )
        try:
            _COLLECTION.insert_one(payload)
        except Exception:
            continue
        return session_id
    raise RuntimeError("Could not create a todo list directory session.")


def save_session(session_id: str, state: Dict[str, Any]) -> None:
    _COLLECTION.update_one(
        {"session_id": str(session_id)},
        {
            "$set": {
                **_state_document(state),
                "updated_at": _now(),
                "expires_at": _expiry(),
            }
        },
        upsert=False,
    )


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    if not session_id:
        return None
    document = _COLLECTION.find_one({"session_id": str(session_id)})
    if not document:
        return None
    return {
        "session_id": str(document.get("session_id") or "").strip(),
        **_state_document(document),
    }
