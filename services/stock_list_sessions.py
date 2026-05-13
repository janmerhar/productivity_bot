import datetime
import uuid
from typing import Any, Dict, Optional

from config.db import mongo_db

_COLLECTION = mongo_db["stock_list_sessions"]
_SESSION_TTL = datetime.timedelta(days=7)


def _ensure_indexes() -> None:
    _COLLECTION.create_index(
        [("session_id", 1)],
        unique=True,
        name="stock_list_sessions_session_id",
    )
    _COLLECTION.create_index(
        [("expires_at", 1)],
        expireAfterSeconds=0,
        name="stock_list_sessions_expires_at_ttl",
    )


_ensure_indexes()


def _now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _expiry() -> datetime.datetime:
    return _now() + _SESSION_TTL


def _state_document(state: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_id": int(state.get("user_id") or 0),
        "guild_id": state.get("guild_id"),
        "channel_id": state.get("channel_id"),
        "kind": str(state.get("kind") or "all").strip(),
        "response_ephemeral": bool(state.get("response_ephemeral", True)),
        "page": max(1, int(state.get("page") or 1)),
        "selected_entry_type": str(state.get("selected_entry_type") or "").strip(),
        "selected_entry_id": str(state.get("selected_entry_id") or "").strip(),
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
    raise RuntimeError("Could not create a stock list session.")


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
