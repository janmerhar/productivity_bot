import datetime
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_UTC = datetime.timezone.utc


def resolve_zoneinfo(timezone_name: Optional[str]) -> Optional[ZoneInfo]:
    value = str(timezone_name or "").strip()
    if not value:
        return None

    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return None


def schedule_timezone_name(schedule: Optional[Mapping[str, Any] | Any]) -> Optional[str]:
    if isinstance(schedule, Mapping):
        return str(schedule.get("timezone") or "").strip() or None

    return str(getattr(schedule, "timezone", "") or "").strip() or None


def runtime_to_aware_datetime(check_datetime: datetime.datetime) -> datetime.datetime:
    if check_datetime.tzinfo is not None and check_datetime.utcoffset() is not None:
        return check_datetime

    local_timezone = datetime.datetime.now().astimezone().tzinfo or _UTC
    return check_datetime.replace(tzinfo=local_timezone)


def runtime_to_utc_naive(check_datetime: datetime.datetime) -> datetime.datetime:
    return runtime_to_aware_datetime(check_datetime).astimezone(_UTC).replace(tzinfo=None)


def cron_match_datetime(
    check_datetime: datetime.datetime,
    timezone_name: Optional[str],
) -> datetime.datetime:
    tzinfo = resolve_zoneinfo(timezone_name)
    if tzinfo is None:
        return check_datetime.replace(tzinfo=None)

    return runtime_to_aware_datetime(check_datetime).astimezone(tzinfo).replace(
        tzinfo=None
    )
