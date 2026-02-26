import datetime
from typing import Any, Dict, List, Optional, Union
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser

from classes.OpenAIFunctions import OpenAIFunctions
from config.env import env


class DueDateService:
    @staticmethod
    def normalize_locale_code(locale_code: Optional[str]) -> Optional[str]:
        cleaned = str(locale_code or "").strip()
        if not cleaned:
            return None
        return cleaned.replace("_", "-")

    @staticmethod
    def timezone_prefers_month_first(timezone: Optional[str]) -> Optional[bool]:
        timezone_value = str(timezone or "").strip()
        if not timezone_value:
            return None
        return timezone_value.startswith("America/")

    @staticmethod
    def locale_prefers_month_first(locale_code: Optional[str]) -> bool:
        normalized = DueDateService.normalize_locale_code(locale_code)
        if not normalized:
            return False
        lowered = normalized.lower()
        return lowered.endswith("-us") or lowered.endswith("-ph")

    @staticmethod
    def prefers_month_first(
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> bool:
        timezone_pref = DueDateService.timezone_prefers_month_first(timezone)
        if timezone_pref is not None:
            return timezone_pref
        return DueDateService.locale_prefers_month_first(locale_code)

    @staticmethod
    def locale_date_order(
        locale_code: Optional[str],
        timezone: Optional[str] = None,
    ) -> str:
        return (
            "MDY"
            if DueDateService.prefers_month_first(
                timezone=timezone, locale_code=locale_code
            )
            else "DMY"
        )

    @staticmethod
    def coerce_due_datetime(
        value: Optional[Union[datetime.datetime, str]],
    ) -> Optional[datetime.datetime]:
        if isinstance(value, datetime.datetime):
            return value
        if not isinstance(value, str):
            return None

        raw = value.strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"

        try:
            return datetime.datetime.fromisoformat(raw)
        except ValueError:
            return None

    @staticmethod
    def parse_due_datetime_local(
        due_text: str,
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        direct = DueDateService.coerce_due_datetime(due_text)
        if direct is not None:
            if direct.tzinfo is not None:
                direct = direct.astimezone().replace(tzinfo=None)
            return direct.replace(second=0, microsecond=0)

        timezone_value = (timezone or "").strip()
        tzinfo = None
        if timezone_value:
            try:
                tzinfo = ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError:
                tzinfo = None

        base_now = datetime.datetime.now(tzinfo) if tzinfo else datetime.datetime.now()
        settings: Dict[str, Any] = {
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": base_now,
            "RETURN_AS_TIMEZONE_AWARE": bool(tzinfo),
            "DATE_ORDER": DueDateService.locale_date_order(
                locale_code,
                timezone=timezone_value,
            ),
        }
        if timezone_value:
            settings["TIMEZONE"] = timezone_value
            settings["TO_TIMEZONE"] = timezone_value

        parsed: Optional[datetime.datetime] = None
        normalized_locale = DueDateService.normalize_locale_code(locale_code)
        locales: List[str] = []
        if normalized_locale:
            locales.append(normalized_locale)
            language = normalized_locale.split("-", 1)[0].strip()
            if language and language not in locales:
                locales.append(language)

        if locales:
            try:
                parsed = dateparser.parse(
                    due_text,
                    locales=locales,
                    settings=settings,
                )
            except Exception:
                parsed = None

        if parsed is None:
            try:
                parsed = dateparser.parse(
                    due_text,
                    settings=settings,
                )
            except Exception:
                parsed = None

        if parsed is None:
            return None

        parsed = parsed.replace(second=0, microsecond=0)
        if parsed.tzinfo is not None:
            return parsed.astimezone().replace(tzinfo=None)
        if tzinfo is not None:
            return parsed.replace(tzinfo=tzinfo).astimezone().replace(tzinfo=None)
        return parsed

    @staticmethod
    def parse_due_datetime(
        due: Optional[str],
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        due_text = due.strip() if due else ""
        if not due_text:
            return None

        local_due_dt = DueDateService.parse_due_datetime_local(
            due_text,
            timezone=timezone,
            locale_code=locale_code,
        )
        if local_due_dt is not None:
            return local_due_dt

        api_key = env.get("OPENAI_API_KEY")
        if api_key:
            due_dt = OpenAIFunctions.parse_due_datetime(
                due_text,
                api_key=api_key,
                timezone=timezone,
            )
            if due_dt is not None:
                return due_dt

        raise ValueError(
            "I couldn't understand that due time. Try 'tomorrow 8pm' "
            "or a date like 03/15/2026 20:00."
        )

    @staticmethod
    def parse_due_input_value(
        due: Optional[str],
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> Optional[str]:
        due_text = (due or "").strip()
        if not due_text:
            return None

        parsed_iso = DueDateService.coerce_due_datetime(due_text)
        if parsed_iso is not None:
            if parsed_iso.tzinfo is not None:
                parsed_iso = parsed_iso.astimezone().replace(tzinfo=None)
            return parsed_iso.isoformat()

        parsed = DueDateService.parse_due_datetime(
            due_text,
            timezone=timezone,
            locale_code=locale_code,
        )
        return parsed.isoformat() if parsed else None

    @staticmethod
    def format_due(
        due: Optional[Union[datetime.datetime, str]],
        locale_code: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> str:
        if due is None:
            return "Not set"

        parsed = DueDateService.coerce_due_datetime(due)
        if parsed is None:
            return str(due)

        timezone_value = (timezone or "").strip()
        if timezone_value:
            try:
                target_tz = ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError:
                target_tz = None

            if target_tz is not None:
                if parsed.tzinfo is None:
                    local_tz = datetime.datetime.now().astimezone().tzinfo
                    if local_tz is not None:
                        parsed = parsed.replace(tzinfo=local_tz)
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(target_tz)

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone().replace(tzinfo=None)
        if DueDateService.prefers_month_first(
            timezone=timezone,
            locale_code=locale_code,
        ):
            return parsed.strftime("%m/%d/%Y %I:%M %p")
        return parsed.strftime("%d/%m/%Y %H:%M")

    @staticmethod
    def due_placeholder(
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> str:
        if DueDateService.prefers_month_first(
            timezone=timezone,
            locale_code=locale_code,
        ):
            return "MM/DD/YYYY HH:MM or tomorrow 5pm"
        return "DD/MM/YYYY HH:MM or tomorrow 17:00"
