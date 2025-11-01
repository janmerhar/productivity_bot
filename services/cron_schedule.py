import datetime
import json
import os
from typing import Optional

from croniter import CroniterBadCronError, croniter
from openai import APIError, OpenAI

from config.env import env


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


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

    def resolve(self, raw: str) -> str:
        expression = raw.strip()
        if not expression:
            raise CronConversionError("Schedule cannot be empty.")

        if self.is_valid(expression):
            return expression

        return self._cron_from_text(expression)

    def is_valid(self, expression: str) -> bool:
        parts = expression.split()
        if len(parts) != 5:
            return False

        try:
            croniter(expression, datetime.datetime.utcnow())
        except (CroniterBadCronError, ValueError):
            return False

        return True

    def _cron_from_text(self, text: str) -> str:
        client = self._get_client()
        system_prompt = (
            "You convert natural language schedules into standard five-field cron expressions "
            "(minute hour day-of-month month day-of-week). "
            "Return JSON with a single key 'cron'. If conversion is impossible, set the value to null. "
            "Use 0-6 for day-of-week, where 0 corresponds to Sunday."
        )
        user_prompt = f"Schedule: {text}"

        response = client.chat.completions.create(
            model=self._model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        message = response.choices[0].message.content
        payload = json.loads(message)

        cron_value = payload["cron"]
        cron_value = cron_value.strip()

        if not self.is_valid(cron_value):
            raise CronConversionError("Model produced an invalid cron expression.")

        return cron_value

    def _get_client(self) -> OpenAI:
        if self._client is not None:
            return self._client

        api_key = self._api_key or env.get("OPENAI_API_KEY")

        self._client = OpenAI(api_key=api_key)
        return self._client


_resolver = CronScheduleResolver()


def resolve_cron_expression(
    raw: str,
    resolver: CronScheduleResolver = _resolver,
) -> str:
    return resolver.resolve(raw)
