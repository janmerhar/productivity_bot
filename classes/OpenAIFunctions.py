import datetime
import json
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openai import APIError, OpenAI

from config.env import env


DEFAULT_OPENAI_MODEL = "gpt-5.4-mini"


class OpenAIFunctions:
    @staticmethod
    def _get_api_key(api_key: Optional[str]) -> Optional[str]:
        return api_key or env.get("OPENAI_API_KEY")

    @staticmethod
    def _get_client(api_key: Optional[str]) -> OpenAI:
        key = OpenAIFunctions._get_api_key(api_key)
        return OpenAI(api_key=key)

    @staticmethod
    def _chat_json_safe(
        system_prompt: str,
        user_prompt: str,
        model: str = DEFAULT_OPENAI_MODEL,
        api_key: Optional[str] = None,
        client: Optional[OpenAI] = None,
    ) -> Optional[Dict[str, Any]]:
        if client is None:
            api_key = OpenAIFunctions._get_api_key(api_key)
            if not api_key:
                return None
            client = OpenAIFunctions._get_client(api_key=api_key)

        try:
            response = client.chat.completions.create(
                model=model,
                temperature=0,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
            )
        except APIError:
            return None

        message = response.choices[0].message.content or ""
        try:
            payload = json.loads(message)
        except json.JSONDecodeError:
            return None

        if not isinstance(payload, dict):
            return None

        return payload

    @staticmethod
    def parse_reminder_time(
        reminder: str,
        api_key: Optional[str] = None,
        model: str = DEFAULT_OPENAI_MODEL,
        timezone: Optional[str] = None,
    ) -> Optional[datetime.time]:
        text = reminder.strip()
        if not text:
            return None

        timezone_value = (timezone or "").strip()
        tzinfo = None
        if timezone_value:
            try:
                tzinfo = ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError:
                tzinfo = None

        now = datetime.datetime.now(tzinfo) if tzinfo else datetime.datetime.now()
        system_prompt = (
            "You convert natural language reminder times into 24-hour local times. "
            "Return JSON with a single key 'time' whose value is in HH:MM format. "
            "If the input cannot be understood, set 'time' to null. "
            "Ignore any dates and return the time only."
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

        time_value = payload.get("time")
        if not time_value:
            return None

        try:
            parsed = datetime.datetime.strptime(str(time_value).strip(), "%H:%M")
        except ValueError:
            return None

        return datetime.time(hour=parsed.hour, minute=parsed.minute)

    @staticmethod
    def parse_due_datetime(
        due: str,
        api_key: Optional[str] = None,
        model: str = DEFAULT_OPENAI_MODEL,
        timezone: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        text = due.strip()
        if not text:
            return None

        timezone_value = (timezone or "").strip()
        tzinfo = None
        if timezone_value:
            try:
                tzinfo = ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError:
                tzinfo = None

        now = datetime.datetime.now(tzinfo) if tzinfo else datetime.datetime.now()
        system_prompt = (
            "You convert natural language due dates into local datetimes. "
            "Return JSON with a single key 'due' whose value is an ISO 8601 datetime "
            "without timezone (YYYY-MM-DDTHH:MM). "
            "If the input cannot be understood, set 'due' to null. "
            "Prefer future dates; if a time would be in the past, choose the next occurrence."
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

        due_value = payload.get("due")
        if not due_value:
            return None

        try:
            due_dt = datetime.datetime.fromisoformat(str(due_value))
        except ValueError:
            return None

        if tzinfo is not None:
            if due_dt.tzinfo is None:
                due_dt = due_dt.replace(tzinfo=tzinfo)
            else:
                due_dt = due_dt.astimezone(tzinfo)
        elif due_dt.tzinfo is not None:
            due_dt = due_dt.astimezone().replace(tzinfo=None)

        due_dt = due_dt.replace(second=0, microsecond=0)
        if due_dt <= now:
            due_dt += datetime.timedelta(days=1)

        if due_dt.tzinfo is not None:
            due_dt = due_dt.astimezone().replace(tzinfo=None)

        return due_dt

    @staticmethod
    def parse_alert_expiration_datetime(
        expires_in: str,
        api_key: Optional[str] = None,
        model: str = DEFAULT_OPENAI_MODEL,
        timezone: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        text = expires_in.strip()
        if not text:
            return None

        timezone_value = (timezone or "").strip()
        tzinfo = None
        if timezone_value:
            try:
                tzinfo = ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError:
                tzinfo = None

        now = datetime.datetime.now(tzinfo) if tzinfo else datetime.datetime.now()
        system_prompt = (
            "You convert natural language alert lifetimes into a future local datetime. "
            "Return JSON with key 'expires_at' in ISO 8601 format without timezone "
            "(YYYY-MM-DDTHH:MM). "
            "If input is invalid or ambiguous, set 'expires_at' to null. "
            "Treat relative durations like 'in 3 days', '2h', 'next week', or "
            "'until tomorrow 8pm' as future points in time."
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

        expires_at_value = payload.get("expires_at")
        if not expires_at_value:
            return None

        try:
            expires_at = datetime.datetime.fromisoformat(str(expires_at_value))
        except ValueError:
            return None

        if tzinfo is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=tzinfo)
            else:
                expires_at = expires_at.astimezone(tzinfo)
        elif expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone().replace(tzinfo=None)

        expires_at = expires_at.replace(second=0, microsecond=0)
        if expires_at <= now:
            return None

        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone().replace(tzinfo=None)

        return expires_at

    @staticmethod
    def parse_cron_expression(
        text: str,
        model: str = DEFAULT_OPENAI_MODEL,
        api_key: Optional[str] = None,
        client: Optional[OpenAI] = None,
        timezone: Optional[str] = None,
    ) -> Optional[str]:
        cleaned = text.strip()
        if not cleaned:
            return None

        if client is None:
            client = OpenAIFunctions._get_client(api_key=api_key)

        system_prompt = (
            "You convert natural language schedules into standard five-field cron expressions "
            "(minute hour day-of-month month day-of-week). "
            "Return JSON with a single key 'cron'. If conversion is impossible, set the value to null. "
            "Use 0-6 for day-of-week, where 0 corresponds to Sunday."
        )
        timezone_value = (timezone or "").strip()
        if timezone_value:
            try:
                tzinfo = ZoneInfo(timezone_value)
            except ZoneInfoNotFoundError:
                tzinfo = None
            now = datetime.datetime.now(tzinfo) if tzinfo else datetime.datetime.now()
            user_prompt = (
                f"Timezone: {timezone_value}\n"
                f"Current local datetime: {now.strftime('%Y-%m-%d %H:%M')}\n"
                f"Schedule: {cleaned}"
            )
        else:
            user_prompt = f"Schedule: {cleaned}"

        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        message = response.choices[0].message.content or ""
        payload = json.loads(message)

        cron_value = payload.get("cron")
        if not cron_value:
            return None

        return str(cron_value).strip()

    @staticmethod
    def rank_stock_candidates(
        query: str,
        candidates: list[dict],
        model: str = DEFAULT_OPENAI_MODEL,
        api_key: Optional[str] = None,
    ) -> list[str]:
        text = (query or "").strip()
        if not text or not candidates:
            return []

        normalized: list[dict[str, str]] = []
        seen_symbols: set[str] = set()

        for item in candidates:
            symbol = str(item.get("symbol") or "").strip().upper()
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            normalized.append(
                {
                    "symbol": symbol,
                    "name": str(item.get("name") or "").strip(),
                    "exchange": str(item.get("exchange") or "").strip(),
                    "quote_type": str(item.get("quote_type") or "").strip().upper(),
                }
            )

        if not normalized:
            return []

        system_prompt = (
            "You rank stock ticker candidates for a user query. "
            "You must choose only from the provided candidates. "
            "Return JSON with key 'symbols' as an ordered array of symbols (best first). "
            "Never invent symbols."
        )
        user_prompt = (
            f"User query: {text}\n"
            f"Candidates: {json.dumps(normalized, ensure_ascii=True)}"
        )

        payload = OpenAIFunctions._chat_json_safe(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            api_key=api_key,
        )
        if not payload:
            return []

        raw_symbols = payload.get("symbols")
        if not isinstance(raw_symbols, list):
            return []

        ranked: list[str] = []
        for value in raw_symbols:
            symbol = str(value or "").strip().upper()
            if symbol in seen_symbols and symbol not in ranked:
                ranked.append(symbol)

        return ranked
