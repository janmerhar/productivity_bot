import datetime
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser

from classes.DailyJob import CronSchedule, DailyJob, OneTimeSchedule2, ScheduleConfig
from classes.DailyJobManager import DailyJobManager
from services.cron_schedule import (
    CronConversionError,
    is_valid_cron_expression,
    resolve_cron_expression,
)
from services.error_reporting import UserVisibleError, ValidationError


class ReminderFunctions:
    ALL_REMINDERS_TOKEN = "__all__"

    @staticmethod
    def _truncate(text: str, limit: int = 60) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3]}..."

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _job_schedule_mode(job: DailyJob) -> str:
        schedule = job.schedule
        if isinstance(schedule, dict):
            return str(schedule.get("mode") or "").strip().lower()
        return str(getattr(schedule, "mode", "") or "").strip().lower()

    @staticmethod
    def is_paused(job: Optional[DailyJob]) -> bool:
        if job is None:
            return False
        return ReminderFunctions._as_bool((job.data or {}).get("paused"))

    @staticmethod
    def reminder_label(job: DailyJob) -> str:
        data = job.data or {}

        if job.type == "stock":
            ticker = str(data.get("ticker") or "").strip().upper()
            if ticker:
                return f"stock: {ticker}"
            return "stock reminder"

        embed_data = data.get("embed")
        if isinstance(embed_data, dict):
            title = str(embed_data.get("title") or "").strip()
            if title:
                return title

        message = str(data.get("message") or "").strip()
        if message:
            first_line = message.splitlines()[0].strip()
            if first_line:
                return ReminderFunctions._truncate(first_line)

        return "Untitled reminder"

    @staticmethod
    def _parse_datetime_string(
        raw: str,
        timezone: Optional[str] = None,
        move_past_forward: bool = False,
    ) -> Optional[datetime.datetime]:
        text = raw.strip()
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
        settings = {
            "PREFER_DATES_FROM": "future",
            "RETURN_AS_TIMEZONE_AWARE": bool(tzinfo),
            "PREFER_DAY_OF_MONTH": "current",
        }
        if timezone_value:
            settings["TIMEZONE"] = timezone_value
            settings["RELATIVE_BASE"] = now

        dt = dateparser.parse(
            text,
            settings=settings,
        )

        if dt is not None:
            if tzinfo is not None and dt.tzinfo is None:
                dt = dt.replace(tzinfo=tzinfo)
            dt = dt.replace(second=0, microsecond=0)
            if move_past_forward and dt <= now:
                dt += datetime.timedelta(days=1)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            return dt

        return None

    @staticmethod
    def parse_time_string(
        raw: str,
        timezone: Optional[str] = None,
    ) -> Optional[datetime.datetime]:
        return ReminderFunctions._parse_datetime_string(
            raw,
            timezone=timezone,
            move_past_forward=True,
        )

    @staticmethod
    def needs_timezone(
        time: str,
        repeat: Optional[str] = None,
        expires_after: Optional[str] = None,
    ) -> bool:
        raw_time = time.strip()
        raw_repeat = (repeat or "").strip()
        raw_expires_after = (expires_after or "").strip()
        return (
            bool(raw_repeat)
            or not is_valid_cron_expression(raw_time)
            or bool(raw_expires_after)
        )

    @staticmethod
    def _resolve_destination_channel_id(
        default_channel_id: Optional[int],
        destination_channel_id: Optional[int],
    ) -> int:
        if destination_channel_id is not None:
            return destination_channel_id

        if default_channel_id is None:
            raise ValidationError("This reminder needs a destination channel.")

        return default_channel_id

    @staticmethod
    def _build_repeat_schedule_input(
        time: str,
        repeat: str,
        skip_days: Optional[str],
    ) -> str:
        raw_time = time.strip()
        raw_repeat = repeat.strip()
        raw_skip_days = (skip_days or "").strip()

        if is_valid_cron_expression(raw_time):
            raise ValidationError(
                "When `repeat` is set, `time` should be a time of day like `8am`, not a cron expression.",
            )

        schedule_input = f"{raw_repeat} at {raw_time}"
        if raw_skip_days:
            schedule_input = f"{schedule_input}, except on {raw_skip_days}"

        return schedule_input

    @staticmethod
    def _looks_like_recurring_schedule(value: str) -> bool:
        text = value.strip().lower()
        if not text:
            return False

        recurring_markers = (
            "every ",
            "everyday",
            "every day",
            "daily",
            "weekly",
            "monthly",
            "yearly",
            "annually",
            "weekdays",
            "weekends",
            "each ",
        )
        return any(marker in text for marker in recurring_markers)

    @staticmethod
    def _parse_expiration(
        expires_after: Optional[str],
        timezone: Optional[str],
        ephemeral: bool,
    ) -> Optional[datetime.datetime]:
        raw_expiration = (expires_after or "").strip()
        if not raw_expiration:
            return None

        expires_at = ReminderFunctions._parse_datetime_string(
            raw_expiration,
            timezone=timezone,
        )
        if expires_at is None:
            raise ValidationError(
                "I couldn't understand `expires_after`.",
                hint="Try `in 2 weeks` or a specific date/time.",
                ephemeral=ephemeral,
            )

        now = datetime.datetime.now().replace(second=0, microsecond=0)
        if expires_at <= now:
            raise ValidationError(
                "`expires_after` needs to be in the future.",
                ephemeral=ephemeral,
            )

        return expires_at

    @staticmethod
    def _build_message_job_data(
        reminder: str,
        ping_text: Optional[str],
        description: Optional[str],
        thumbnail_url: Optional[str],
        expires_at: Optional[datetime.datetime],
    ) -> Dict[str, Any]:
        title = reminder.strip()
        body = (description or "").strip()
        mention_text = (ping_text or "").strip()

        if not title:
            raise ValidationError("Reminder text cannot be empty.")

        message_lines = []
        if mention_text:
            message_lines.append(mention_text)
        if not body and not (thumbnail_url or "").strip():
            message_lines.append(title)

        payload: Dict[str, Any] = {"message": "\n".join(message_lines).strip()}

        if body or (thumbnail_url or "").strip():
            embed_payload: Dict[str, Any] = {"title": title}
            if body:
                embed_payload["description"] = body
            if (thumbnail_url or "").strip():
                embed_payload["thumbnail_url"] = thumbnail_url.strip()
            payload["embed"] = embed_payload

        if expires_at is not None:
            payload["expires_at"] = expires_at.isoformat()
        payload["source"] = "reminder"

        return payload

    @staticmethod
    def _build_stock_job_data(
        reminder: str,
        ping_text: Optional[str],
        description: Optional[str],
        thumbnail_url: Optional[str],
        expires_at: Optional[datetime.datetime],
        ephemeral: bool,
    ) -> Tuple[str, Dict[str, Any]]:
        if (thumbnail_url or "").strip():
            raise ValidationError(
                "Stock reminders do not support `thumbnail_url` yet.",
                ephemeral=ephemeral,
            )

        stock_value = reminder.strip()[6:].strip()
        stock_tokens = [
            token.strip().upper()
            for token in stock_value.replace(",", " ").split()
            if token.strip()
        ]
        if not stock_tokens:
            raise ValidationError(
                "Please provide a stock ticker after `stock:`.",
                ephemeral=ephemeral,
            )
        if len(stock_tokens) != 1:
            raise ValidationError(
                "Please provide exactly one stock ticker after `stock:`.",
                ephemeral=ephemeral,
            )

        symbol = stock_tokens[0]
        header_lines = []
        mention_text = (ping_text or "").strip()
        if mention_text:
            header_lines.append(mention_text)
        if (description or "").strip():
            header_lines.append(description.strip())

        payload: Dict[str, Any] = {"ticker": symbol}
        if header_lines:
            payload["header"] = "\n".join(header_lines)
        if expires_at is not None:
            payload["expires_at"] = expires_at.isoformat()
        payload["source"] = "reminder"

        return symbol, payload

    @staticmethod
    def is_reminder_job(job: Optional[DailyJob]) -> bool:
        if job is None:
            return False

        data = job.data or {}
        if str(data.get("source") or "").strip().lower() == "reminder":
            return True

        # Backward compatibility for one-time reminders created before
        # reminder-specific metadata was stored.
        return (
            ReminderFunctions._job_schedule_mode(job) == "one-time"
            and job.type in {"message", "stock"}
        )

    @staticmethod
    def delete_reminder(
        reminder_id: str,
        guild_id: Optional[int],
    ) -> bool:
        manager = DailyJobManager()
        normalized_id = reminder_id.strip()
        job = manager.get_job(
            normalized_id,
            guild_id=guild_id,
        )
        if job is None:
            return False

        if not ReminderFunctions.is_reminder_job(job):
            raise ValidationError("That ID belongs to a scheduled job, not a reminder.")

        return manager.delete_job(
            normalized_id,
            guild_id=guild_id,
        )

    @staticmethod
    def list_reminders(
        guild_id: Optional[int],
        paused: Optional[bool] = None,
    ) -> List[DailyJob]:
        manager = DailyJobManager()
        jobs = manager.list_jobs(guild_id=guild_id)
        reminders = []
        for job in jobs:
            if not ReminderFunctions.is_reminder_job(job):
                continue
            if paused is not None and ReminderFunctions.is_paused(job) != paused:
                continue
            reminders.append(job)
        reminders.sort(key=lambda job: str(job.id))
        return reminders

    @staticmethod
    def pause_all_reminders(guild_id: Optional[int]) -> int:
        manager = DailyJobManager()
        reminders = ReminderFunctions.list_reminders(guild_id, paused=False)
        paused_count = 0

        for job in reminders:
            data = dict(job.data or {})
            data["paused"] = True
            data["source"] = "reminder"
            updated = manager.update_job(
                str(job.id),
                data=data,
                guild_id=guild_id,
            )
            if updated:
                paused_count += 1

        return paused_count

    @staticmethod
    def pause_reminder(
        reminder_id: str,
        guild_id: Optional[int],
    ) -> str:
        manager = DailyJobManager()
        normalized_id = reminder_id.strip()
        job = manager.get_job(
            normalized_id,
            guild_id=guild_id,
        )
        if job is None:
            return "missing"

        if not ReminderFunctions.is_reminder_job(job):
            raise ValidationError("That ID belongs to a scheduled job, not a reminder.")

        data = dict(job.data or {})
        if ReminderFunctions._as_bool(data.get("paused")):
            return "already_paused"

        data["paused"] = True
        data["source"] = "reminder"

        updated = manager.update_job(
            normalized_id,
            data=data,
            guild_id=guild_id,
        )
        return "paused" if updated else "missing"

    @staticmethod
    def resume_reminder(
        reminder_id: str,
        guild_id: Optional[int],
    ) -> str:
        manager = DailyJobManager()
        normalized_id = reminder_id.strip()
        job = manager.get_job(
            normalized_id,
            guild_id=guild_id,
        )
        if job is None:
            return "missing"

        if not ReminderFunctions.is_reminder_job(job):
            raise ValidationError("That ID belongs to a scheduled job, not a reminder.")

        data = dict(job.data or {})
        if not ReminderFunctions._as_bool(data.get("paused")):
            return "already_resumed"

        data["paused"] = False
        data["source"] = "reminder"

        updated = manager.update_job(
            normalized_id,
            data=data,
            guild_id=guild_id,
        )
        return "resumed" if updated else "missing"

    @staticmethod
    def resume_all_reminders(guild_id: Optional[int]) -> int:
        manager = DailyJobManager()
        reminders = ReminderFunctions.list_reminders(guild_id, paused=True)
        resumed_count = 0

        for job in reminders:
            data = dict(job.data or {})
            data["paused"] = False
            data["source"] = "reminder"
            updated = manager.update_job(
                str(job.id),
                data=data,
                guild_id=guild_id,
            )
            if updated:
                resumed_count += 1

        return resumed_count

    @staticmethod
    def create_reminder(
        guild_id: Optional[int],
        default_channel_id: Optional[int],
        reminder: str,
        time: str,
        repeat: Optional[str] = None,
        ping_text: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        skip_days: Optional[str] = None,
        description: Optional[str] = None,
        expires_after: Optional[str] = None,
        destination_channel_id: Optional[int] = None,
        ephemeral: bool = True,
        timezone: Optional[str] = None,
    ) -> Tuple[DailyJob, str]:
        raw_time = time.strip()
        raw_repeat = (repeat or "").strip()
        raw_skip_days = (skip_days or "").strip()
        expires_at = ReminderFunctions._parse_expiration(
            expires_after,
            timezone,
            ephemeral,
        )
        channel_id = ReminderFunctions._resolve_destination_channel_id(
            default_channel_id,
            destination_channel_id,
        )
        destination_label = f"<#{channel_id}>"

        if raw_skip_days and not raw_repeat and not is_valid_cron_expression(raw_time):
            if not ReminderFunctions._looks_like_recurring_schedule(raw_time):
                raise ValidationError(
                    "`skip_days` only applies to recurring reminders.",
                    ephemeral=ephemeral,
                )

        schedule_config: ScheduleConfig
        schedule_label: str
        job_type = "message"

        if raw_repeat:
            schedule_input = ReminderFunctions._build_repeat_schedule_input(
                raw_time,
                raw_repeat,
                raw_skip_days,
            )
            try:
                cron_expression = resolve_cron_expression(
                    schedule_input,
                    timezone=timezone,
                )
            except CronConversionError as exc:
                raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

            schedule_config = CronSchedule(expression=cron_expression)
            schedule_label = f"`{schedule_input}` (Cron: `{cron_expression}`)"
        elif is_valid_cron_expression(raw_time):
            if raw_skip_days:
                raise ValidationError(
                    "`skip_days` cannot be combined with a raw cron expression.",
                    ephemeral=ephemeral,
                )
            schedule_config = CronSchedule(expression=raw_time)
            schedule_label = f"`{raw_time}` (Cron: `{raw_time}`)"
        elif ReminderFunctions._looks_like_recurring_schedule(raw_time):
            schedule_input = raw_time
            if raw_skip_days:
                schedule_input = f"{schedule_input}, except on {raw_skip_days}"
            try:
                cron_expression = resolve_cron_expression(
                    schedule_input,
                    timezone=timezone,
                )
            except CronConversionError as exc:
                raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

            schedule_config = CronSchedule(expression=cron_expression)
            schedule_label = f"`{schedule_input}` (Cron: `{cron_expression}`)"
        else:
            scheduled_dt = ReminderFunctions.parse_time_string(
                raw_time,
                timezone=timezone,
            )
            if scheduled_dt is None:
                raise ValidationError(
                    "I couldn't understand that time.",
                    hint="Try `08:30`, `8pm`, or use a cron expression.",
                    ephemeral=ephemeral,
                )
            if expires_at is not None and expires_at <= scheduled_dt:
                raise ValidationError(
                    "`expires_after` must be later than the reminder time.",
                    ephemeral=ephemeral,
                )
            schedule_config = OneTimeSchedule2(datetime=scheduled_dt.isoformat())
            schedule_label = f"`{scheduled_dt.strftime('%Y-%m-%d %H:%M')}`"

        if reminder.strip().lower().startswith("stock:"):
            symbol, job_data = ReminderFunctions._build_stock_job_data(
                reminder,
                ping_text,
                description,
                thumbnail_url,
                expires_at,
                ephemeral,
            )
            job_type = "stock"
            if isinstance(schedule_config, CronSchedule):
                confirmation = (
                    f"Scheduled recurring stock reminder for `{symbol}` in {destination_label} on {schedule_label}."
                )
            else:
                confirmation = (
                    f"Got it! I'll post stock price for `{symbol}` in {destination_label} at {schedule_label}."
                )
        else:
            job_data = ReminderFunctions._build_message_job_data(
                reminder,
                ping_text,
                description,
                thumbnail_url,
                expires_at,
            )
            if isinstance(schedule_config, CronSchedule):
                confirmation = (
                    f"Scheduled recurring reminder in {destination_label} on {schedule_label}."
                )
            else:
                confirmation = (
                    f"Got it! I'll post that reminder in {destination_label} at {schedule_label}."
                )

        manager = DailyJobManager()
        try:
            created_job = manager.insert_job(
                guild_id,
                channel_id,
                job_type,
                job_data,
                schedule_config,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while scheduling that reminder. Please try again.",
                ephemeral=ephemeral,
                cause=exc,
            )

        return created_job, confirmation
