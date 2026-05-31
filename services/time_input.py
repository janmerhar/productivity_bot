import datetime
import re
from typing import Optional, Tuple


_DOTTED_TIME_PATTERN = re.compile(
    r"(?<![\d.])(?P<hour>[01]?\d|2[0-3])\.(?P<minute>[0-5]\d)(?![\d.])"
)
_EXPLICIT_DOTTED_TIME_PATTERN = re.compile(
    r"(?P<prefix>\b(?:at|around|by|before|after)\s+)"
    r"(?P<time>(?P<hour>[01]?\d|2[0-3])\.(?P<minute>[0-5]\d))"
    r"(?![\d.])",
    re.IGNORECASE,
)
_RELATIVE_DOTTED_TIME_PATTERN = re.compile(
    r"^(?P<prefix>\s*(?:today|tomorrow|tonight)\s+)"
    r"(?P<time>(?P<hour>[01]?\d|2[0-3])\.(?P<minute>[0-5]\d))"
    r"(?P<suffix>\s*)$",
    re.IGNORECASE,
)
_CLOCK_TIME_PATTERN = re.compile(
    r"^\s*(?P<hour>[01]?\d|2[0-3]):(?P<minute>[0-5]\d)\s*$"
)
_WEEKDAY_TIME_PATTERN = re.compile(
    r"^\s*(?:next\s+)?"
    r"(?P<weekday>mon(?:day)?|tue(?:sday)?|wed(?:nesday)?|"
    r"thu(?:rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
    r"\s+(?:at\s+)?"
    r"(?P<hour>\d{1,2})"
    r"(?::(?P<minute>[0-5]\d))?"
    r"\s*(?P<meridiem>a\.?m\.?|p\.?m\.?)?\s*$",
    re.IGNORECASE,
)
_WEEKDAY_NUMBERS = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


def _dotted_time_match_could_be_date(match: re.Match[str]) -> bool:
    return (
        1 <= int(match.group("hour")) <= 31
        and 1 <= int(match.group("minute")) <= 12
    )


def is_ambiguous_standalone_dotted_value(value: str) -> bool:
    """Return whether a bare dotted token could reasonably be a date or time."""

    text = str(value or "")
    match = _DOTTED_TIME_PATTERN.fullmatch(text.strip())
    if match is None:
        return False

    return _dotted_time_match_could_be_date(match)


def normalize_dotted_time_notation(
    value: str,
    *,
    time_only: bool = False,
) -> str:
    """Normalize dotted clock tokens only when they cannot be mistaken for dates."""

    text = str(value or "")
    replacer = lambda match: f"{match.group('hour')}:{match.group('minute')}"
    unambiguous_replacer = lambda match: (
        match.group(0)
        if _dotted_time_match_could_be_date(match)
        else replacer(match)
    )
    if time_only:
        return _DOTTED_TIME_PATTERN.sub(replacer, text)

    text = _EXPLICIT_DOTTED_TIME_PATTERN.sub(
        lambda match: f"{match.group('prefix')}{replacer(match)}",
        text,
    )
    text = _RELATIVE_DOTTED_TIME_PATTERN.sub(
        lambda match: (
            f"{match.group('prefix')}{replacer(match)}{match.group('suffix')}"
        ),
        text,
    )

    if is_ambiguous_standalone_dotted_value(text):
        return text

    return _DOTTED_TIME_PATTERN.sub(unambiguous_replacer, text)


def parse_clock_time(
    value: str,
    *,
    allow_ambiguous_dotted: bool = False,
) -> Optional[datetime.time]:
    """Parse a standalone local clock time, including dotted HH.MM notation."""

    match = _CLOCK_TIME_PATTERN.fullmatch(
        normalize_dotted_time_notation(value, time_only=allow_ambiguous_dotted)
    )
    if match is None:
        return None

    return datetime.time(
        hour=int(match.group("hour")),
        minute=int(match.group("minute")),
    )


def parse_weekday_clock_time(value: str) -> Optional[Tuple[int, datetime.time]]:
    """Parse a singular weekday with a local clock time."""

    match = _WEEKDAY_TIME_PATTERN.fullmatch(
        normalize_dotted_time_notation(value, time_only=True)
    )
    if match is None:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    meridiem = str(match.group("meridiem") or "").lower().replace(".", "")
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour %= 12
        if meridiem == "pm":
            hour += 12
    elif hour > 23:
        return None

    weekday = _WEEKDAY_NUMBERS[match.group("weekday")[:3].lower()]
    return weekday, datetime.time(hour=hour, minute=minute)
