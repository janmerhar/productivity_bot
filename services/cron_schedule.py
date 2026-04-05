import datetime
from typing import Optional

from croniter import CroniterBadCronError, croniter
from openai import OpenAI

from classes.OpenAIFunctions import OpenAIFunctions, DEFAULT_OPENAI_MODEL


class CronConversionError(Exception):
    """Raised when a schedule string cannot be turned into a cron expression."""


class CronScheduleResolver:
    """Encapsulates cron validation and natural-language conversion."""

    def __init__(
        self,
        model: str = DEFAULT_OPENAI_MODEL,
        client: Optional[OpenAI] = None,
        api_key: Optional[str] = None,
    ) -> None:
        self._model = model
        self._client = client
        self._api_key = api_key

    def resolve(self, raw: str, timezone: Optional[str] = None) -> str:
        expression = raw.strip()
        if not expression:
            raise CronConversionError("Schedule cannot be empty.")

        if self.is_valid(expression):
            return expression

        return self._cron_from_text(expression, timezone=timezone)

    def is_valid(self, expression: str) -> bool:
        parts = expression.split()
        if len(parts) != 5:
            return False

        try:
            croniter(expression, datetime.datetime.utcnow())
        except (CroniterBadCronError, ValueError):
            return False

        return True

    def _cron_from_text(self, text: str, timezone: Optional[str] = None) -> str:
        cron_value = OpenAIFunctions.parse_cron_expression(
            text,
            model=self._model,
            client=self._get_client(),
            api_key=self._api_key,
            timezone=timezone,
        )
        if not cron_value:
            raise CronConversionError("Schedule could not be parsed.")

        if not self.is_valid(cron_value):
            raise CronConversionError("Model produced an invalid cron expression.")

        return cron_value

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client

        self._client = OpenAIFunctions._get_client(api_key=self._api_key)
        return self._client


_resolver = CronScheduleResolver()


def resolve_cron_expression(
    raw: str,
    resolver: CronScheduleResolver = _resolver,
    timezone: Optional[str] = None,
) -> str:
    return resolver.resolve(raw, timezone=timezone)


def is_valid_cron_expression(
    raw: str,
    resolver: CronScheduleResolver = _resolver,
) -> bool:
    return resolver.is_valid(raw.strip())
