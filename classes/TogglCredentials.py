from typing import Optional

from classes.UserSettingsFunctions import UserSettingsFunctions
from config.db import mongo_db


class TogglCredentials:
    @staticmethod
    def set_key(guild_id: int, user_id: int, api_key: str) -> None:
        cleaned = api_key.strip()
        UserSettingsFunctions.set_toggl_api_key(user_id=user_id, api_key=cleaned)
        mongo_db["toggl_credentials"].delete_many({"user_id": user_id})

    @staticmethod
    def get_key(guild_id: int, user_id: int) -> Optional[str]:
        key = UserSettingsFunctions.get_toggl_api_key(
            user_id=user_id,
            guild_id=guild_id,
        )
        if key:
            return key

        # Legacy fallback from old collection + inline migration.
        doc = mongo_db["toggl_credentials"].find_one(
            {"guild_id": guild_id, "user_id": user_id}
        )
        if not doc:
            doc = mongo_db["toggl_credentials"].find_one({"user_id": user_id})
        if not doc:
            return None
        value = doc.get("api_key")
        cleaned = str(value).strip() if value else None
        if not cleaned:
            return None

        try:
            UserSettingsFunctions.set_toggl_api_key(user_id=user_id, api_key=cleaned)
        except Exception:
            return cleaned

        return cleaned

    @staticmethod
    def clear_key(guild_id: int, user_id: int) -> bool:
        removed_settings = UserSettingsFunctions.clear_toggl_api_key(user_id=user_id)
        result = mongo_db["toggl_credentials"].delete_many({"user_id": user_id})
        return removed_settings or result.deleted_count > 0
