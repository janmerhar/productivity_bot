import datetime
import re
from dataclasses import dataclass
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from classes.OpenAIFunctions import DEFAULT_OPENAI_MODEL, OpenAIFunctions
from config.env import env
from services.due_datetime import DueDateService


@dataclass(frozen=True)
class ParsedTogglTimeEntry:
    start: datetime.datetime
    stop: datetime.datetime
    duration_seconds: int


class TogglTimeEntryService:
    @staticmethod
    def parse_insert_range(
        start_text: str,
        stop_text: str,
        *,
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> ParsedTogglTimeEntry:
        start_dt = TogglTimeEntryService.parse_datetime(
            start_text,
            timezone=timezone,
            locale_code=locale_code,
        )
        if start_dt is None:
            raise ValueError(
                "I couldn't understand the `start` time. Try `yesterday 14:00` "
                "or `2026-03-20 14:00`."
            )

        stop_dt = TogglTimeEntryService.parse_datetime(
            stop_text,
            timezone=timezone,
            locale_code=locale_code,
        )
        if stop_dt is None:
            raise ValueError(
                "I couldn't understand the `stop` time. Try `yesterday 16:00` "
                "or `2026-03-20 16:00`."
            )

        now = datetime.datetime.now(TogglTimeEntryService._resolve_tzinfo(timezone))
        if start_dt > now or stop_dt > now:
            raise ValueError("Inserted timers must be in the past.")
        if stop_dt <= start_dt:
            raise ValueError("`stop` must be later than `start`.")

        duration_seconds = int((stop_dt - start_dt).total_seconds())
        return ParsedTogglTimeEntry(
            start=start_dt,
            stop=stop_dt,
            duration_seconds=duration_seconds,
        )

    @staticmethod
    def parse_datetime(
        raw: str,
        *,
        timezone: Optional[str] = None,
        locale_code: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        text = str(raw or "").strip()
        if not text:
            return None

        tzinfo = TogglTimeEntryService._resolve_tzinfo(timezone)
        direct = DueDateService.coerce_due_datetime(text)
        if direct is not None:
            return TogglTimeEntryService._normalize_direct_datetime(direct, tzinfo)

        parsed_local = DueDateService.parse_due_datetime_local(
            text,
            timezone=timezone,
            locale_code=locale_code,
        )
        if parsed_local is not None:
            return TogglTimeEntryService._runtime_naive_to_aware(parsed_local)

        parsed = TogglTimeEntryService._parse_datetime_ai(
            text,
            timezone=timezone,
        )
        if parsed is not None:
            return parsed

        return None

    @staticmethod
    def parse_tags(raw: Optional[str]) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []

        tokens = [
            token.strip()
            for token in re.split(r"[\s,]+", text)
            if token and token.strip()
        ]

        deduped: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            lowered = token.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(token)

        return deduped

    @staticmethod
    def normalize_billable(value: Optional[Any]) -> Optional[bool]:
        if value is None:
            return None
        if isinstance(value, bool):
            return value

        text = str(value).strip().lower()
        if not text:
            return None
        if text in {"true", "yes", "y", "1", "billable"}:
            return True
        if text in {"false", "no", "n", "0", "non-billable", "nonbillable"}:
            return False

        raise ValueError("`billable` must be true or false.")

    @staticmethod
    def to_toggl_timestamp(value: datetime.datetime) -> str:
        utc_value = value.astimezone(datetime.timezone.utc).replace(microsecond=0)
        return utc_value.isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_datetime_ai(
        text: str,
        *,
        timezone: Optional[str] = None,
        model: str = DEFAULT_OPENAI_MODEL,
    ) -> Optional[datetime.datetime]:
        api_key = env.get("OPENAI_API_KEY")
        if not api_key:
            return None

        tzinfo = TogglTimeEntryService._resolve_tzinfo(timezone)
        now = datetime.datetime.now(tzinfo)
        timezone_value = str(timezone or "").strip()
        system_prompt = (
            "You convert natural language timestamps for manually inserted Toggl "
            "time entries into local datetimes. Return JSON with a single key "
            "'datetime' whose value is an ISO 8601 datetime without timezone "
            "(YYYY-MM-DDTHH:MM). If the input cannot be understood, set "
            "'datetime' to null. Prefer the most plausible past datetime."
        )
        timezone_line = (
            f"Timezone: {timezone_value}\n"
            if timezone_value
            else "Timezone: server local timezone\n"
        )
        user_prompt = (
            timezone_line
            + f"Current local datetime: {now.strftime('%Y-%m-%d %H:%M')}\n"
            + f"Input: {text}"
        )

        payload = OpenAIFunctions._chat_json_safe(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            api_key=api_key,
        )
        if not payload:
            return None

        raw_value = payload.get("datetime")
        if not raw_value:
            return None

        try:
            parsed = datetime.datetime.fromisoformat(str(raw_value).strip())
        except ValueError:
            return None

        return TogglTimeEntryService._to_timezone_aware(parsed, tzinfo)

    @staticmethod
    def _resolve_tzinfo(timezone: Optional[str]) -> datetime.tzinfo:
        timezone_value = str(timezone or "").strip()
        if timezone_value:
            try:
                return ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError:
                pass

        return datetime.datetime.now().astimezone().tzinfo or datetime.timezone.utc

    @staticmethod
    def _runtime_naive_to_aware(value: datetime.datetime) -> datetime.datetime:
        runtime_tz = datetime.datetime.now().astimezone().tzinfo or datetime.timezone.utc
        return value.replace(tzinfo=runtime_tz, second=0, microsecond=0)

    @staticmethod
    def _normalize_direct_datetime(
        value: datetime.datetime,
        tzinfo: datetime.tzinfo,
    ) -> datetime.datetime:
        normalized = value.replace(second=0, microsecond=0)
        if normalized.tzinfo is None:
            return normalized.replace(tzinfo=tzinfo)
        return normalized.astimezone(datetime.timezone.utc).astimezone(
            datetime.datetime.now().astimezone().tzinfo or datetime.timezone.utc
        )

    @staticmethod
    def _to_timezone_aware(
        value: datetime.datetime,
        tzinfo: datetime.tzinfo,
    ) -> datetime.datetime:
        normalized = value.replace(second=0, microsecond=0)
        if normalized.tzinfo is None:
            return normalized.replace(tzinfo=tzinfo)
        return normalized.astimezone(tzinfo)
