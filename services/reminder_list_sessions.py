import datetime
import uuid
from typing import Any, Dict, Optional

from config.db import mongo_db

_COLLECTION = mongo_db["reminder_list_sessions"]
_SESSION_TTL = datetime.timedelta(days=7)


def _ensure_indexes() -> None:
    _COLLECTION.create_index(
        [("session_id", 1)],
        unique=True,
        name="reminder_list_sessions_session_id",
    )
    _COLLECTION.create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="reminder_list_sessions_expires_at_ttl",
    )


_ensure_indexes()


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _expiry() -> datetime.datetime:
    return _now() + _SESSION_TTL


def _state_document(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "scope_label": str(state.get("scope_label") or "").strip(),
        "target_value": str(state.get("target_value") or "").strip(),
        "status_filter": str(state.get("status_filter") or "all").strip(),
        "guild_id": state.get("guild_id"),
        "channel_id": state.get("channel_id"),
        "destination_type": state.get("destination_type"),
        "user_id": state.get("user_id"),
        "sort": str(state.get("sort") or "ascending").strip(),
        "response_ephemeral": bool(state.get("response_ephemeral", False)),
        "page": max(1, int(state.get("page") or 1)),
        "search_query": str(state.get("search_query") or ""),
        "ping_filter_user_ids": [
            int(user_id)
            for user_id in list(state.get("ping_filter_user_ids") or [])
        ][:25],
        "ping_filter_label": str(state.get("ping_filter_label") or "All").strip()
        or "All",
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
    raise RuntimeError("Could not create a reminder list session.")


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


def delete_session(session_id: str) -> None:
    if not session_id:
        return
    _COLLECTION.delete_one({"session_id": str(session_id)})
