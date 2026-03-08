import datetime
import re
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
from services.schedule_time import schedule_timezone_name


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
            description = str(embed_data.get("description") or "").strip()
            if description:
                first_line = description.splitlines()[0].strip()
                if first_line:
                    return ReminderFunctions._truncate(first_line)

        message = str(data.get("message") or "").strip()
        if message:
            ping_text, body_text = ReminderFunctions._split_message_content(message)
            first_line = body_text.splitlines()[0].strip() if body_text else ""
            if first_line:
                return ReminderFunctions._truncate(first_line)
            if ping_text:
                return "Ping reminder"

        return "Untitled reminder"

    @staticmethod
    def _looks_like_mention_token(token: str) -> bool:
        cleaned = token.strip()
        if not cleaned:
            return False
        return bool(
            re.fullmatch(r"<@!?\d+>|<@&\d+>|@everyone|@here", cleaned)
        )

    @staticmethod
    def _split_message_content(raw_message: str) -> Tuple[Optional[str], str]:
        lines = [line.strip() for line in str(raw_message or "").splitlines()]
        mention_lines: List[str] = []
        body_lines: List[str] = []
        collecting_mentions = True

        for line in lines:
            if (
                collecting_mentions
                and line
                and all(
                    ReminderFunctions._looks_like_mention_token(token)
                    for token in line.split()
                )
            ):
                mention_lines.append(line)
                continue

            collecting_mentions = False
            body_lines.append(line)

        mention_text = "\n".join(mention_lines).strip() or None
        body_text = "\n".join(body_lines).strip()
        return mention_text, body_text

    @staticmethod
    def schedule_input_for_job(job: DailyJob) -> str:
        schedule = job.schedule
        mode = ReminderFunctions._job_schedule_mode(job)

        if isinstance(schedule, dict):
            raw_datetime = str(schedule.get("datetime") or "").strip()
            raw_expression = str(schedule.get("expression") or "").strip()
        else:
            raw_datetime = str(getattr(schedule, "datetime", "") or "").strip()
            raw_expression = str(getattr(schedule, "expression", "") or "").strip()

        if mode == "cron":
            return raw_expression

        if mode == "one-time":
            if not raw_datetime:
                return ""
            try:
                return datetime.datetime.fromisoformat(raw_datetime).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except ValueError:
                return raw_datetime

        return raw_expression or raw_datetime

    @staticmethod
    def expiration_input_for_job(job: DailyJob) -> str:
        raw_value = str((job.data or {}).get("expires_at") or "").strip()
        if not raw_value:
            return ""
        try:
            return datetime.datetime.fromisoformat(raw_value).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return raw_value

    @staticmethod
    def reminder_edit_values(job: DailyJob) -> Dict[str, str]:
        data = job.data or {}
        schedule = ReminderFunctions.schedule_input_for_job(job)
        expires_after = ReminderFunctions.expiration_input_for_job(job)

        if job.type == "stock":
            header_text = str(data.get("header") or "").strip()
            ping_text, description = ReminderFunctions._split_message_content(header_text)
            reminder = str(data.get("ticker") or "").strip().upper()
            return {
                "schedule": schedule,
                "reminder": reminder,
                "description": description,
                "thumbnail_url": "",
                "expires_after": expires_after,
                "ping_text": ping_text or "",
                "destination_channel": (
                    f"<#{job.channel_id}>" if job.channel_id is not None else ""
                ),
            }

        message_text = str(data.get("message") or "").strip()
        ping_text, body_text = ReminderFunctions._split_message_content(message_text)
        embed_data = data.get("embed")
        embed_payload = embed_data if isinstance(embed_data, dict) else {}

        reminder = str(embed_payload.get("title") or "").strip() or body_text
        description = str(embed_payload.get("description") or "").strip()
        thumbnail_url = str(embed_payload.get("thumbnail_url") or "").strip()

        return {
            "schedule": schedule,
            "reminder": reminder,
            "description": description,
            "thumbnail_url": thumbnail_url,
            "expires_after": expires_after,
            "ping_text": ping_text or "",
            "destination_channel": (
                f"<#{job.channel_id}>" if job.channel_id is not None else ""
            ),
        }

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
    def _resolve_schedule(
        time: str,
        repeat: Optional[str],
        skip_days: Optional[str],
        expires_at: Optional[datetime.datetime],
        ephemeral: bool,
        timezone: Optional[str],
    ) -> Tuple[ScheduleConfig, str]:
        raw_time = time.strip()
        raw_repeat = (repeat or "").strip()
        raw_skip_days = (skip_days or "").strip()

        if raw_skip_days and not raw_repeat and not is_valid_cron_expression(raw_time):
            if not ReminderFunctions._looks_like_recurring_schedule(raw_time):
                raise ValidationError(
                    "`skip_days` only applies to recurring reminders.",
                    ephemeral=ephemeral,
                )

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

            return (
                CronSchedule(expression=cron_expression, timezone=timezone),
                f"`{schedule_input}` (Cron: `{cron_expression}`)",
            )

        if is_valid_cron_expression(raw_time):
            if raw_skip_days:
                raise ValidationError(
                    "`skip_days` cannot be combined with a raw cron expression.",
                    ephemeral=ephemeral,
                )
            return (
                CronSchedule(expression=raw_time, timezone=timezone),
                f"`{raw_time}` (Cron: `{raw_time}`)",
            )

        if ReminderFunctions._looks_like_recurring_schedule(raw_time):
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

            return (
                CronSchedule(expression=cron_expression, timezone=timezone),
                f"`{schedule_input}` (Cron: `{cron_expression}`)",
            )

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

        return (
            OneTimeSchedule2(datetime=scheduled_dt.isoformat()),
            f"`{scheduled_dt.strftime('%Y-%m-%d %H:%M')}`",
        )

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
    def get_reminder(
        reminder_id: str,
        guild_id: Optional[int],
    ) -> Optional[DailyJob]:
        manager = DailyJobManager()
        normalized_id = reminder_id.strip()
        job = manager.get_job(
            normalized_id,
            guild_id=guild_id,
        )
        if job is None:
            return None

        if not ReminderFunctions.is_reminder_job(job):
            raise ValidationError("That ID belongs to a scheduled job, not a reminder.")

        return job

    @staticmethod
    def list_reminders(
        guild_id: Optional[int],
        paused: Optional[bool] = None,
        channel_id: Optional[int] = None,
    ) -> List[DailyJob]:
        manager = DailyJobManager()
        jobs = manager.list_jobs(guild_id=guild_id, channel_id=channel_id)
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
    def update_reminder(
        reminder_id: str,
        guild_id: Optional[int],
        time: str,
        reminder: str,
        ping_text: Optional[str] = None,
        description: Optional[str] = None,
        expires_after: Optional[str] = None,
        destination_channel_id: Optional[int] = None,
        ephemeral: bool = True,
        timezone: Optional[str] = None,
    ) -> DailyJob:
        manager = DailyJobManager()
        normalized_id = reminder_id.strip()
        job = ReminderFunctions.get_reminder(normalized_id, guild_id)
        if job is None:
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        existing_data = dict(job.data or {})
        edit_values = ReminderFunctions.reminder_edit_values(job)
        existing_schedule_timezone = schedule_timezone_name(job.schedule)
        raw_ping_text = ping_text.strip() if ping_text is not None else None
        raw_description = description.strip() if description is not None else None
        raw_expires_after = expires_after
        if raw_expires_after is None:
            raw_expires_after = str(existing_data.get("expires_at") or "").strip()
        else:
            raw_expires_after = raw_expires_after.strip()
            if raw_expires_after.lower() in {"none", "clear", "off"}:
                raw_expires_after = ""

        expires_at = (
            ReminderFunctions._parse_expiration(
                raw_expires_after,
                timezone,
                ephemeral,
            )
            if raw_expires_after
            else None
        )
        schedule_config, _ = ReminderFunctions._resolve_schedule(
            time,
            repeat=None,
            skip_days=None,
            expires_at=expires_at,
            ephemeral=ephemeral,
            timezone=timezone or existing_schedule_timezone,
        )

        updated_data: Dict[str, Any]
        managed_keys = {"expires_at", "source", "paused"}

        if job.type == "stock":
            effective_ping_text = (
                edit_values.get("ping_text") if raw_ping_text is None else raw_ping_text
            ) or None
            effective_description = (
                edit_values.get("description")
                if raw_description is None
                else raw_description
            ) or None
            normalized_reminder = reminder.strip()
            if not normalized_reminder.lower().startswith("stock:"):
                normalized_reminder = f"stock: {normalized_reminder}"
            _, updated_data = ReminderFunctions._build_stock_job_data(
                normalized_reminder,
                effective_ping_text,
                effective_description,
                None,
                expires_at,
                ephemeral,
            )
            managed_keys.update({"ticker", "header"})
        else:
            if reminder.strip().lower().startswith("stock:"):
                raise ValidationError(
                    "Changing a message reminder into a stock reminder is not supported.",
                    ephemeral=ephemeral,
                )
            effective_ping_text = (
                edit_values.get("ping_text") if raw_ping_text is None else raw_ping_text
            ) or None
            effective_description = (
                edit_values.get("description")
                if raw_description is None
                else raw_description
            ) or None
            effective_thumbnail_url = edit_values.get("thumbnail_url") or None
            updated_data = ReminderFunctions._build_message_job_data(
                reminder,
                effective_ping_text,
                effective_description,
                effective_thumbnail_url,
                expires_at,
            )
            managed_keys.update({"message", "embed"})

        for key, value in existing_data.items():
            if key in managed_keys or key in updated_data:
                continue
            updated_data[key] = value

        if "paused" in existing_data:
            updated_data["paused"] = existing_data["paused"]
        updated_data["source"] = "reminder"

        updated = manager.update_job(
            normalized_id,
            data=updated_data,
            schedule=schedule_config,
            new_channel_id=destination_channel_id,
            guild_id=guild_id,
        )
        if not updated:
            raise ValidationError(
                "No reminder found with that ID in this server.",
                ephemeral=ephemeral,
            )

        updated_job = manager.get_job(
            normalized_id,
            guild_id=guild_id,
        )
        if updated_job is None:
            raise UserVisibleError(
                "Reminder updated, but it could not be reloaded.",
                ephemeral=ephemeral,
            )

        return updated_job

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

        schedule_config, schedule_label = ReminderFunctions._resolve_schedule(
            time,
            repeat,
            skip_days,
            expires_at,
            ephemeral,
            timezone,
        )
        job_type = "message"

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
