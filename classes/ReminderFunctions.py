import datetime
import re
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser

from classes.DailyJob import CronSchedule, DailyJob, OneTimeSchedule2, ScheduleConfig
from classes.DailyJobManager import DailyJobManager
from classes.OpenAIFunctions import OpenAIFunctions
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
    def destination_type(job: DailyJob) -> str:
        raw_value = str((job.data or {}).get("destination_type") or "").strip().lower()
        return raw_value if raw_value == "private" else "channel"

    @staticmethod
    def destination_user_id(job: DailyJob) -> Optional[int]:
        raw_value = (job.data or {}).get("user_id")
        return raw_value if isinstance(raw_value, int) else None

    @staticmethod
    def is_private_destination(job: DailyJob) -> bool:
        return ReminderFunctions.destination_type(job) == "private"

    @staticmethod
    def destination_label(job: DailyJob) -> str:
        if ReminderFunctions.is_private_destination(job):
            return "Private"
        if job.channel_id is None:
            return "unknown"
        return f"<#{job.channel_id}>"

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
        data = job.data or {}
        if not ReminderFunctions._as_bool(data.get("paused")):
            return False

        pause_until = ReminderFunctions.pause_until_for_job(job)
        if pause_until is None:
            return True

        now = datetime.datetime.now().replace(second=0, microsecond=0)
        return pause_until.replace(second=0, microsecond=0) > now

    @staticmethod
    def pause_until_for_job(job: Optional[DailyJob]) -> Optional[datetime.datetime]:
        if job is None:
            return None

        raw_value = str((job.data or {}).get("pause_until") or "").strip()
        if not raw_value:
            return None

        try:
            return datetime.datetime.fromisoformat(raw_value)
        except ValueError:
            return None

    @staticmethod
    def reminder_label(job: DailyJob) -> str:
        data = job.data or {}

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
    def pause_until_input_for_job(job: DailyJob) -> str:
        raw_value = str((job.data or {}).get("pause_until") or "").strip()
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
        expires = ReminderFunctions.expiration_input_for_job(job)

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
            "expires": expires,
            "until": expires,
            "ping_text": ping_text or "",
            "notify_in_dms": (
                "yes"
                if ReminderFunctions._as_bool(data.get("notify_ping_users_in_dm"))
                else ""
            ),
            "destination_channel": ReminderFunctions.destination_label(job),
        }

    @staticmethod
    def notify_ping_users_in_dm(job: DailyJob) -> bool:
        return ReminderFunctions._as_bool(
            (job.data or {}).get("notify_ping_users_in_dm")
        )

    @staticmethod
    def ping_user_ids(job: DailyJob) -> List[int]:
        ping_text = str(ReminderFunctions.reminder_edit_values(job).get("ping_text") or "")
        user_ids: List[int] = []
        seen: set[int] = set()
        for raw_id in re.findall(r"<@!?(\d+)>", ping_text):
            try:
                user_id = int(raw_id)
            except ValueError:
                continue
            if user_id in seen:
                continue
            seen.add(user_id)
            user_ids.append(user_id)
        return user_ids

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
        schedule: str,
        expires: Optional[str] = None,
        until: Optional[str] = None,
    ) -> bool:
        raw_schedule = schedule.strip()
        raw_expires = (expires or "").strip()
        raw_until = (until or "").strip()
        return (
            not is_valid_cron_expression(raw_schedule)
            or bool(raw_expires)
            or bool(raw_until)
        )

    @staticmethod
    def _resolve_destination(
        default_channel_id: Optional[int],
        destination_channel_id: Optional[int],
        destination_type: str,
        destination_user_id: Optional[int],
        ephemeral: bool,
    ) -> Tuple[int, str, Dict[str, Any]]:
        normalized_destination_type = (
            destination_type.strip().lower() if destination_type else "channel"
        )

        if normalized_destination_type == "private":
            if destination_user_id is None:
                raise ValidationError(
                    "Private reminders need a user to deliver to.",
                    ephemeral=ephemeral,
                )
            anchor_channel_id = (
                destination_channel_id
                if destination_channel_id is not None
                else default_channel_id
            )
            if anchor_channel_id is None:
                raise ValidationError(
                    "This reminder needs a destination channel.",
                    ephemeral=ephemeral,
                )
            return (
                anchor_channel_id,
                "Private",
                {
                    "destination_type": "private",
                    "user_id": destination_user_id,
                },
            )

        if destination_channel_id is not None:
            return (
                destination_channel_id,
                f"<#{destination_channel_id}>",
                {"destination_type": "channel"},
            )

        if default_channel_id is None:
            raise ValidationError(
                "This reminder needs a destination channel.",
                ephemeral=ephemeral,
            )

        return default_channel_id, f"<#{default_channel_id}>", {"destination_type": "channel"}

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
        expires: Optional[str],
        timezone: Optional[str],
        ephemeral: bool,
    ) -> Optional[datetime.datetime]:
        raw_expiration = (expires or "").strip()
        if not raw_expiration:
            return None

        expires_at = ReminderFunctions._parse_datetime_string(
            raw_expiration,
            timezone=timezone,
        )
        if expires_at is None:
            raise ValidationError(
                "I couldn't understand `expires`.",
                hint="Try `in 2 weeks` or a specific date/time.",
                ephemeral=ephemeral,
            )

        now = datetime.datetime.now().replace(second=0, microsecond=0)
        if expires_at <= now:
            raise ValidationError(
                "`expires` needs to be in the future.",
                ephemeral=ephemeral,
            )

        return expires_at

    @staticmethod
    def _parse_pause_until(
        until: Optional[str],
        timezone: Optional[str],
        ephemeral: bool,
    ) -> Optional[datetime.datetime]:
        raw_until = (until or "").strip()
        if not raw_until:
            return None

        pause_until = ReminderFunctions._parse_datetime_string(
            raw_until,
            timezone=timezone,
        )
        if pause_until is None:
            raise ValidationError(
                "I couldn't understand `until`.",
                hint="Try `tomorrow 9am` or a specific date/time.",
                ephemeral=ephemeral,
            )

        now = datetime.datetime.now().replace(second=0, microsecond=0)
        if pause_until <= now:
            raise ValidationError(
                "`until` needs to be in the future.",
                ephemeral=ephemeral,
            )

        return pause_until

    @staticmethod
    def _ai_resolve_schedule(
        raw_schedule: str,
        timezone: Optional[str],
    ) -> Optional[Tuple[ScheduleConfig, str]]:
        payload = OpenAIFunctions.parse_reminder_schedule(
            raw_schedule,
            timezone=timezone,
        )
        if not payload:
            return None

        kind = str(payload.get("kind") or "").strip().lower()
        if kind == "cron":
            cron_expression = str(payload.get("cron") or "").strip()
            if not is_valid_cron_expression(cron_expression):
                return None
            return (
                CronSchedule(expression=cron_expression, timezone=timezone),
                f"`{raw_schedule}` (Cron: `{cron_expression}`)",
            )

        if kind != "datetime":
            return None

        raw_datetime = str(payload.get("datetime") or "").strip()
        if not raw_datetime:
            return None

        try:
            scheduled_dt = datetime.datetime.fromisoformat(raw_datetime)
        except ValueError:
            return None

        scheduled_dt = scheduled_dt.replace(second=0, microsecond=0)
        if scheduled_dt.tzinfo is not None:
            scheduled_dt = scheduled_dt.astimezone().replace(tzinfo=None)

        return (
            OneTimeSchedule2(datetime=scheduled_dt.isoformat()),
            f"`{scheduled_dt.strftime('%Y-%m-%d %H:%M')}`",
        )

    @staticmethod
    def _build_message_job_data(
        reminder: str,
        ping_text: Optional[str],
        description: Optional[str],
        thumbnail_url: Optional[str],
        expires_at: Optional[datetime.datetime],
        notify_ping_users_in_dm: bool = False,
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
        if notify_ping_users_in_dm:
            payload["notify_ping_users_in_dm"] = True
        payload["source"] = "reminder"

        return payload

    @staticmethod
    def _resolve_schedule(
        schedule: str,
        expires_at: Optional[datetime.datetime],
        ephemeral: bool,
        timezone: Optional[str],
    ) -> Tuple[ScheduleConfig, str]:
        raw_schedule = schedule.strip()

        if is_valid_cron_expression(raw_schedule):
            return (
                CronSchedule(expression=raw_schedule, timezone=timezone),
                f"`{raw_schedule}` (Cron: `{raw_schedule}`)",
            )

        if ReminderFunctions._looks_like_recurring_schedule(raw_schedule):
            try:
                cron_expression = resolve_cron_expression(
                    raw_schedule,
                    timezone=timezone,
                )
            except CronConversionError as exc:
                ai_schedule = ReminderFunctions._ai_resolve_schedule(
                    raw_schedule,
                    timezone,
                )
                if ai_schedule is not None:
                    schedule_config, schedule_label = ai_schedule
                    if isinstance(schedule_config, CronSchedule):
                        return schedule_config, schedule_label

                    raw_datetime = str(schedule_config.datetime or "").strip()
                    try:
                        scheduled_dt = datetime.datetime.fromisoformat(raw_datetime)
                    except ValueError:
                        pass
                    else:
                        if expires_at is not None and expires_at <= scheduled_dt:
                            raise ValidationError(
                                "`expires` must be later than the reminder time.",
                                ephemeral=ephemeral,
                            )
                        return (
                            OneTimeSchedule2(datetime=scheduled_dt.isoformat()),
                            schedule_label,
                        )
                raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

            return (
                CronSchedule(expression=cron_expression, timezone=timezone),
                f"`{raw_schedule}` (Cron: `{cron_expression}`)",
            )

        scheduled_dt = ReminderFunctions.parse_time_string(
            raw_schedule,
            timezone=timezone,
        )
        if scheduled_dt is None:
            ai_schedule = ReminderFunctions._ai_resolve_schedule(
                raw_schedule,
                timezone,
            )
            if ai_schedule is not None:
                schedule_config, schedule_label = ai_schedule
                if isinstance(schedule_config, CronSchedule):
                    return schedule_config, schedule_label

                raw_datetime = str(schedule_config.datetime or "").strip()
                try:
                    scheduled_dt = datetime.datetime.fromisoformat(raw_datetime)
                except ValueError:
                    scheduled_dt = None
                else:
                    if expires_at is not None and expires_at <= scheduled_dt:
                        raise ValidationError(
                            "`expires` must be later than the reminder time.",
                            ephemeral=ephemeral,
                        )
                    return (
                        OneTimeSchedule2(datetime=scheduled_dt.isoformat()),
                        schedule_label,
                    )

            raise ValidationError(
                "I couldn't understand that schedule.",
                hint=(
                    "Try `08:30`, `tomorrow 8pm`, `every weekday at 9am`, "
                    "or use a cron expression."
                ),
                ephemeral=ephemeral,
            )
        if expires_at is not None and expires_at <= scheduled_dt:
            raise ValidationError(
                "`expires` must be later than the reminder time.",
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
            and job.type == "message"
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
        destination_type: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> List[DailyJob]:
        manager = DailyJobManager()
        jobs = manager.list_jobs(guild_id=guild_id, channel_id=channel_id)
        reminders = []
        for job in jobs:
            if not ReminderFunctions.is_reminder_job(job):
                continue
            if paused is not None and ReminderFunctions.is_paused(job) != paused:
                continue
            if (
                destination_type is not None
                and ReminderFunctions.destination_type(job) != destination_type
            ):
                continue
            if (
                destination_type == "private"
                and user_id is not None
                and ReminderFunctions.destination_user_id(job) != user_id
            ):
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
            data.pop("pause_until", None)
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
        until: Optional[str] = None,
        timezone: Optional[str] = None,
        ephemeral: bool = True,
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
        pause_until = ReminderFunctions._parse_pause_until(
            until,
            timezone,
            ephemeral,
        )
        existing_pause_until = ReminderFunctions.pause_until_for_job(job)
        pause_state_changed = not ReminderFunctions.is_paused(job)
        pause_until_changed = (
            pause_until is not None
            and (
                existing_pause_until is None
                or existing_pause_until.replace(second=0, microsecond=0)
                != pause_until.replace(second=0, microsecond=0)
            )
        )

        if not pause_state_changed and not pause_until_changed:
            return "already_paused"

        data["paused"] = True
        if pause_until is not None:
            data["pause_until"] = pause_until.isoformat()
        elif not ReminderFunctions.is_paused(job):
            data.pop("pause_until", None)
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
        had_pause_until = bool(str(data.get("pause_until") or "").strip())
        if not ReminderFunctions.is_paused(job) and not had_pause_until:
            return "already_resumed"

        data["paused"] = False
        data.pop("pause_until", None)
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
            data.pop("pause_until", None)
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
        schedule: str,
        reminder: str,
        ping_text: Optional[str] = None,
        description: Optional[str] = None,
        expires: Optional[str] = None,
        notify_ping_users_in_dm: Optional[bool] = None,
        destination_channel_id: Optional[int] = None,
        destination_type: Optional[str] = None,
        destination_user_id: Optional[int] = None,
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
        effective_destination_type = (
            destination_type
            if destination_type is not None
            else ReminderFunctions.destination_type(job)
        )
        existing_schedule_timezone = schedule_timezone_name(job.schedule)
        raw_ping_text = ping_text.strip() if ping_text is not None else None
        raw_description = description.strip() if description is not None else None
        effective_notify_ping_users_in_dm = (
            ReminderFunctions.notify_ping_users_in_dm(job)
            if notify_ping_users_in_dm is None
            else bool(notify_ping_users_in_dm)
        )
        raw_expires = expires
        if raw_expires is None:
            raw_expires = str(existing_data.get("expires_at") or "").strip()
        else:
            raw_expires = raw_expires.strip()
            if raw_expires.lower() in {"none", "clear", "off"}:
                raw_expires = ""

        expires_at = (
            ReminderFunctions._parse_expiration(
                raw_expires,
                timezone,
                ephemeral,
            )
            if raw_expires
            else None
        )
        schedule_config, _ = ReminderFunctions._resolve_schedule(
            schedule,
            expires_at=expires_at,
            ephemeral=ephemeral,
            timezone=timezone or existing_schedule_timezone,
        )

        managed_keys = {"expires_at", "notify_ping_users_in_dm", "source", "paused"}
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
            effective_notify_ping_users_in_dm,
        )
        managed_keys.update({"message", "embed"})

        for key, value in existing_data.items():
            if key in managed_keys or key in updated_data:
                continue
            updated_data[key] = value

        if "paused" in existing_data:
            updated_data["paused"] = existing_data["paused"]
        updated_data["source"] = "reminder"
        updated_data["destination_type"] = (
            "private"
            if str(effective_destination_type).strip().lower() == "private"
            else "channel"
        )
        if destination_user_id is not None:
            updated_data["user_id"] = destination_user_id
        elif updated_data["destination_type"] != "private":
            updated_data.pop("user_id", None)

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
        schedule: str,
        ping_text: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        description: Optional[str] = None,
        expires: Optional[str] = None,
        notify_ping_users_in_dm: bool = False,
        destination_channel_id: Optional[int] = None,
        destination_type: str = "channel",
        destination_user_id: Optional[int] = None,
        ephemeral: bool = True,
        timezone: Optional[str] = None,
    ) -> Tuple[DailyJob, str]:
        expires_at = ReminderFunctions._parse_expiration(
            expires,
            timezone,
            ephemeral,
        )
        channel_id, destination_label, destination_data = ReminderFunctions._resolve_destination(
            default_channel_id,
            destination_channel_id,
            destination_type,
            destination_user_id,
            ephemeral,
        )

        schedule_config, schedule_label = ReminderFunctions._resolve_schedule(
            schedule,
            expires_at,
            ephemeral,
            timezone,
        )

        job_data = ReminderFunctions._build_message_job_data(
            reminder,
            ping_text,
            description,
            thumbnail_url,
            expires_at,
            notify_ping_users_in_dm,
        )
        if isinstance(schedule_config, CronSchedule):
            confirmation = (
                f"Scheduled recurring reminder in {destination_label} on {schedule_label}."
            )
        else:
            confirmation = (
                f"Got it! I'll post that reminder in {destination_label} at {schedule_label}."
            )

        job_data.update(destination_data)

        manager = DailyJobManager()
        try:
            created_job = manager.insert_job(
                guild_id,
                channel_id,
                "message",
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
