import datetime
from typing import Optional

from config.db import mongo_db


class TogglCredentials:
    @staticmethod
    def set_key(guild_id: int, user_id: int, api_key: str) -> None:
        cleaned = api_key.strip()
        now = datetime.datetime.utcnow().isoformat()
        mongo_db["toggl_credentials"].update_one(
            {"guild_id": guild_id, "user_id": user_id},
            {
                "$set": {
                    "api_key": cleaned,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    @staticmethod
    def get_key(guild_id: int, user_id: int) -> Optional[str]:
        doc = mongo_db["toggl_credentials"].find_one(
            {"guild_id": guild_id, "user_id": user_id}
        )
        if not doc:
            return None
        value = doc.get("api_key")
        return str(value).strip() if value else None

    @staticmethod
    def clear_key(guild_id: int, user_id: int) -> bool:
        result = mongo_db["toggl_credentials"].delete_one(
            {"guild_id": guild_id, "user_id": user_id}
        )
        return result.deleted_count > 0
