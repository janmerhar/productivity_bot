import datetime
import json
from typing import Optional, Dict, Any

from openai import APIError, OpenAI

from config.env import env


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


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
    ) -> Optional[datetime.time]:
        text = reminder.strip()
        if not text:
            return None

        now = datetime.datetime.now()
        system_prompt = (
            "You convert natural language reminder times into 24-hour local times. "
            "Return JSON with a single key 'time' whose value is in HH:MM format. "
            "If the input cannot be understood, set 'time' to null. "
            "Ignore any dates and return the time only."
        )
        user_prompt = (
            f"Current local datetime: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"Input: {text}"
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
    ) -> Optional[datetime.datetime]:
        text = due.strip()
        if not text:
            return None

        now = datetime.datetime.now()
        system_prompt = (
            "You convert natural language due dates into local datetimes. "
            "Return JSON with a single key 'due' whose value is an ISO 8601 datetime "
            "without timezone (YYYY-MM-DDTHH:MM). "
            "If the input cannot be understood, set 'due' to null. "
            "Prefer future dates; if a time would be in the past, choose the next occurrence."
        )
        user_prompt = (
            f"Current local datetime: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"Input: {text}"
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

        if due_dt.tzinfo is not None:
            due_dt = due_dt.astimezone().replace(tzinfo=None)

        due_dt = due_dt.replace(second=0, microsecond=0)
        if due_dt <= now:
            due_dt += datetime.timedelta(days=1)

        return due_dt

    @staticmethod
    def parse_alert_expiration_datetime(
        expires_in: str,
        api_key: Optional[str] = None,
        model: str = DEFAULT_OPENAI_MODEL,
    ) -> Optional[datetime.datetime]:
        text = expires_in.strip()
        if not text:
            return None

        now = datetime.datetime.now()
        system_prompt = (
            "You convert natural language alert lifetimes into a future local datetime. "
            "Return JSON with key 'expires_at' in ISO 8601 format without timezone "
            "(YYYY-MM-DDTHH:MM). "
            "If input is invalid or ambiguous, set 'expires_at' to null. "
            "Treat relative durations like 'in 3 days', '2h', 'next week', or "
            "'until tomorrow 8pm' as future points in time."
        )
        user_prompt = (
            f"Current local datetime: {now.strftime('%Y-%m-%d %H:%M')}\n"
            f"Input: {text}"
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

        if expires_at.tzinfo is not None:
            expires_at = expires_at.astimezone().replace(tzinfo=None)

        expires_at = expires_at.replace(second=0, microsecond=0)
        if expires_at <= now:
            return None

        return expires_at

    @staticmethod
    def parse_cron_expression(
        text: str,
        model: str = DEFAULT_OPENAI_MODEL,
        api_key: Optional[str] = None,
        client: Optional[OpenAI] = None,
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
