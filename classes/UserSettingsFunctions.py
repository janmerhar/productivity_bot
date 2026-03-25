import datetime
import re
import threading
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cachetools import TTLCache
from pymongo import ReturnDocument

from classes.OpenAIFunctions import OpenAIFunctions, DEFAULT_OPENAI_MODEL
from classes.UserSettings import UserSettings
from config.db import mongo_db


_TIMEZONE_ALIASES = {
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "pacific": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "mst": "America/Denver",
    "mdt": "America/Denver",
    "mountain": "America/Denver",
    "mt": "America/Denver",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "central": "America/Chicago",
    "ct": "America/Chicago",
    "est": "America/New_York",
    "edt": "America/New_York",
    "eastern": "America/New_York",
    "et": "America/New_York",
    "berlin": "Europe/Berlin",
    "ljubljana": "Europe/Ljubljana",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "tokyo": "Asia/Tokyo",
    "sydney": "Australia/Sydney",
}


class UserSettingsFunctions:
    # Cache up to 5000 user settings for 7 days (604800 seconds)
    _cache = TTLCache(maxsize=5000, ttl=604800.0)
    _cache_lock = threading.RLock()

    @staticmethod
    def _collection():
        return mongo_db["user_settings"]

    @staticmethod
    def fetch(user_id: int, *, force_refresh: bool = False) -> UserSettings:
        key = int(user_id)
        if not force_refresh:
            cached = UserSettingsFunctions._cache_get(key)
            if cached is not None:
                return cached

        document = UserSettingsFunctions._collection().find_one({"user_id": key})
        settings = UserSettings.from_document(document, user_id=key)
        UserSettingsFunctions._cache_put(settings)
        return settings

    @staticmethod
    def get_timezone(user_id: int) -> Optional[str]:
        settings = UserSettingsFunctions.fetch(user_id)
        timezone = settings.timezone
        if not isinstance(timezone, str):
            return None
        validated = UserSettingsFunctions._validate_timezone_identifier(timezone)
        return validated

    @staticmethod
    def set_timezone(user_id: int, timezone: str) -> UserSettings:
        key = int(user_id)
        resolved = UserSettingsFunctions._validate_timezone_identifier(timezone)
        if not resolved:
            raise ValueError("Invalid timezone identifier.")

        now = datetime.datetime.utcnow().isoformat()
        updated_doc = UserSettingsFunctions._collection().find_one_and_update(
            {"user_id": key},
            {
                "$set": {
                    "user_id": key,
                    "timezone": resolved,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        settings = UserSettings.from_document(updated_doc, user_id=key)
        UserSettingsFunctions._cache_put(settings)
        return settings

    @staticmethod
    def get_toggl_api_key(user_id: int) -> Optional[str]:
        settings = UserSettingsFunctions.fetch(user_id)
        key = settings.toggl_api_key
        if not isinstance(key, str):
            return None

        cleaned = key.strip()
        return cleaned or None

    @staticmethod
    def get_toggl_workspace_id(user_id: int) -> Optional[int]:
        settings = UserSettingsFunctions.fetch(user_id)
        workspace_id = settings.toggl_workspace_id
        if workspace_id is None:
            return None
        try:
            return int(workspace_id)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def set_toggl_api_key(
        user_id: int,
        api_key: str,
        workspace_id: Optional[int] = None,
    ) -> UserSettings:
        key = int(user_id)
        cleaned = api_key.strip()
        if not cleaned:
            raise ValueError("API key cannot be empty.")

        cleaned_workspace_id: Optional[int]
        if workspace_id is None:
            cleaned_workspace_id = None
        else:
            try:
                cleaned_workspace_id = int(workspace_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("Workspace id must be an integer.") from exc

        now = datetime.datetime.utcnow().isoformat()
        updated_doc = UserSettingsFunctions._collection().find_one_and_update(
            {"user_id": key},
            {
                "$set": {
                    "user_id": key,
                    "toggl_api_key": cleaned,
                    "toggl_workspace_id": cleaned_workspace_id,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        settings = UserSettings.from_document(updated_doc, user_id=key)
        UserSettingsFunctions._cache_put(settings)
        return settings

    @staticmethod
    def set_toggl_workspace_id(user_id: int, workspace_id: int) -> UserSettings:
        key = int(user_id)
        try:
            cleaned_workspace_id = int(workspace_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("Workspace id must be an integer.") from exc

        now = datetime.datetime.utcnow().isoformat()
        updated_doc = UserSettingsFunctions._collection().find_one_and_update(
            {"user_id": key},
            {
                "$set": {
                    "user_id": key,
                    "toggl_workspace_id": cleaned_workspace_id,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        settings = UserSettings.from_document(updated_doc, user_id=key)
        UserSettingsFunctions._cache_put(settings)
        return settings

    @staticmethod
    def clear_toggl_api_key(user_id: int) -> bool:
        key = int(user_id)
        existed = UserSettingsFunctions.get_toggl_api_key(user_id) is not None
        now = datetime.datetime.utcnow().isoformat()
        updated_doc = UserSettingsFunctions._collection().find_one_and_update(
            {"user_id": key},
            {
                "$unset": {
                    "toggl_api_key": "",
                    "toggl_workspace_id": "",
                },
                "$set": {
                    "updated_at": now,
                },
            },
            upsert=False,
            return_document=ReturnDocument.AFTER,
        )
        if updated_doc:
            settings = UserSettings.from_document(updated_doc, user_id=key)
            UserSettingsFunctions._cache_put(settings)
        else:
            UserSettingsFunctions.invalidate_cache(key)
        return existed

    @staticmethod
    def resolve_timezone_input(
        raw: str,
        model: str = DEFAULT_OPENAI_MODEL,
    ) -> Optional[str]:
        text = raw.strip()
        if not text:
            return None

        validated = UserSettingsFunctions._validate_timezone_identifier(text)
        if validated:
            return validated

        alias = _TIMEZONE_ALIASES.get(text.lower())
        if alias:
            return alias

        offset_match = re.match(
            r"^(?:utc|gmt)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?$",
            text.lower(),
        )
        if offset_match:
            sign, hours_text, minutes_text = offset_match.groups()
            hours = int(hours_text)
            minutes = int(minutes_text or "0")
            if 0 <= hours <= 14 and minutes == 0:
                # Etc/GMT uses an inverted sign: UTC+2 => Etc/GMT-2
                etc_sign = "-" if sign == "+" else "+"
                return f"Etc/GMT{etc_sign}{hours}"

        ai_guess = UserSettingsFunctions._resolve_timezone_input_ai(text, model=model)
        if ai_guess:
            return ai_guess

        return None

    @staticmethod
    def _resolve_timezone_input_ai(
        text: str,
        model: str = DEFAULT_OPENAI_MODEL,
    ) -> Optional[str]:
        system_prompt = (
            "You convert user-provided timezone text into a valid IANA timezone identifier. "
            "Return JSON with a single key 'timezone'. "
            "If conversion is impossible, set the value to null. "
            "Examples of valid outputs: America/New_York, Europe/Ljubljana, Asia/Tokyo."
        )
        user_prompt = f"Input timezone text: {text}"

        payload: Optional[Dict[str, Any]] = OpenAIFunctions._chat_json_safe(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
        )
        if not payload:
            return None

        timezone_value = payload.get("timezone")
        if not timezone_value:
            return None

        return UserSettingsFunctions._validate_timezone_identifier(str(timezone_value))

    @staticmethod
    def _validate_timezone_identifier(raw: str) -> Optional[str]:
        candidate = raw.strip()
        if not candidate:
            return None

        if candidate.upper() in {"UTC", "GMT"}:
            return "Etc/UTC"

        try:
            ZoneInfo(candidate)
        except ZoneInfoNotFoundError:
            return None

        return candidate

    @staticmethod
    def invalidate_cache(user_id: int) -> None:
        key = int(user_id)
        with UserSettingsFunctions._cache_lock:
            UserSettingsFunctions._cache.pop(key, None)

    @staticmethod
    def clear_cache() -> None:
        with UserSettingsFunctions._cache_lock:
            UserSettingsFunctions._cache.clear()

    @staticmethod
    def _cache_get(user_id: int) -> Optional[UserSettings]:
        with UserSettingsFunctions._cache_lock:
            return UserSettingsFunctions._cache.get(int(user_id))

    @staticmethod
    def _cache_put(settings: UserSettings) -> None:
        key = int(settings.user_id)
        with UserSettingsFunctions._cache_lock:
            UserSettingsFunctions._cache[key] = settings
