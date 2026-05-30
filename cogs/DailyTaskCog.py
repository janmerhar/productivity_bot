import asyncio
import logging
import json
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from classes.DailyJob import CronSchedule, DailyJob
from classes.DailyJobManager import DailyJobManager
from config.env import settings
from classes.PomodoroFunctions import PomodoroFunctions
from classes.ReminderFunctions import ReminderFunctions
from classes.TodoFunctions import TodoFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from embeds.HabitEmbeds import HabitEmbeds
from embeds.PomodoroEmbeds import PomodoroEmbeds
from embeds.TodoEmbeds import TodoEmbeds
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from views.PomodoroRestartView import PomodoroRestartView
from views.PomodoroStartView import PomodoroStartView
from classes.HabitFunctions import HabitFunctions
from services.discord_helpers import (
    resolve_messageable_channel,
    resolve_reminder_destination,
)
from views.ScheduledJobActionView import ScheduledJobActionView
from services.cron_schedule import (
    CronConversionError,
    is_valid_cron_expression,
    resolve_cron_expression,
)
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import (
    VISIBILITY_CHOICES,
    VISIBILITY_DESC,
    resolve_visibility_for_context,
)
from views.ReminderOutputView import ReminderOutputView


class ScheduledJobDeliveryUnavailable(Exception):
    """Raised when a scheduled job should be retried after a delivery failure."""


class DailyTaskCog(commands.Cog):
    if not settings.jobs_commands_disabled:
        jobs = app_commands.Group(name="jobs", description="Manage scheduled jobs")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @staticmethod
    def _resolve_response_visibility(
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]],
    ) -> bool:
        return resolve_visibility_for_context(
            interaction.guild_id,
            visibility,
            guild_default="private",
        )

    @staticmethod
    def _coerce_int_id(value: Any) -> Optional[int]:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def _send_reminder_ping_dms(
        self,
        job: DailyJob,
        *,
        message_payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not ReminderFunctions.notify_ping_users_in_dm(job):
            return

        user_ids = ReminderFunctions.ping_user_ids(job)
        if not user_ids:
            return

        destination_user_id = (
            ReminderFunctions.destination_user_id(job)
            if ReminderFunctions.is_private_destination(job)
            else None
        )
        guild = self.bot.get_guild(job.guild_id) if job.guild_id is not None else None

        for user_id in user_ids:
            if destination_user_id is not None and user_id == destination_user_id:
                continue

            user = self.bot.get_user(user_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(user_id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

            try:
                if job.type == "message":
                    reminder_view = ReminderOutputView(
                        job=job,
                        guild=guild,
                        result_message="Reminder triggered.",
                        ok=True,
                        user_id=user_id,
                        response_ephemeral=False,
                    )
                    dm_payload = reminder_view.response_payload()
                    posted_message = await user.send(**dm_payload)
                    reminder_view.message = posted_message
                    continue

                dm_payload = dict(message_payload or {})
                content = str(dm_payload.get("content") or "").strip()
                if content:
                    _, body_text = ReminderFunctions._split_message_content(content)
                    if body_text:
                        dm_payload["content"] = body_text
                    else:
                        dm_payload.pop("content", None)

                if not dm_payload:
                    continue

                await user.send(**dm_payload)
            except discord.HTTPException:
                logging.getLogger(__name__).exception(
                    "Failed to DM reminder recipient",
                    extra={"user_id": user_id, "job_id": str(job.id)},
                )

    @commands.Cog.listener()
    async def on_ready(self):
        print("DailyTaskCog cog loaded")
        if not self._runner.is_running():
            self._runner.start()

    def cog_unload(self) -> None:
        if self._runner.is_running():
            self._runner.cancel()

    if not settings.jobs_commands_disabled:
        @jobs.command(name="create", description="Create a recurring job")
        @app_commands.describe(
            schedule="Cron expression or natural language schedule",
            type="Type of the job to create",
            data="Payload for the job; plain text for message jobs and ticker/coin id for crypto jobs",
            visibility=VISIBILITY_DESC,
        )
        @app_commands.choices(
            type=[
                app_commands.Choice(name="Crypto", value="crypto"),
                app_commands.Choice(name="Message", value="message"),
            ],
            visibility=VISIBILITY_CHOICES,
        )
        async def job(
            self,
            interaction: discord.Interaction,
            schedule: str,
            type: app_commands.Choice[str],
            data: str,
            visibility: Optional[app_commands.Choice[str]] = None,
        ) -> None:
            ephemeral = self._resolve_response_visibility(interaction, visibility)
            timezone = None
            if not is_valid_cron_expression(schedule):
                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    await self._create_job(
                        interaction=followup_interaction,
                        schedule=schedule,
                        job_type=type.value,
                        data=data,
                        ephemeral=ephemeral,
                        timezone=resolved_timezone,
                    )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing `/jobs create`.",
                    response_ephemeral=ephemeral,
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=ephemeral)
            await self._create_job(
                interaction=interaction,
                schedule=schedule,
                job_type=type.value,
                data=data,
                ephemeral=ephemeral,
                timezone=timezone,
            )

    async def _create_job(
        self,
        interaction: discord.Interaction,
        schedule: str,
        job_type: str,
        data: str,
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        try:
            cron_expression = await asyncio.to_thread(
                resolve_cron_expression,
                schedule,
                timezone=timezone,
            )
        except CronConversionError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

        raw_data = data.strip()
        if job_type == "message":
            payload: Dict[str, Any] = {"message": raw_data}
        elif job_type == "crypto":
            payload = {"tickers": [raw_data]}
        else:
            payload = {"message": raw_data}

        manager = DailyJobManager()
        schedule_config = CronSchedule(
            expression=cron_expression,
            timezone=timezone,
        )

        try:
            created_job = await asyncio.to_thread(
                manager.insert_job,
                interaction.guild_id,
                interaction.channel_id,
                job_type,
                payload,
                schedule_config,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while storing that job. Please try again.",
                ephemeral=ephemeral,
                cause=exc,
            )

        await interaction.followup.send(
            ephemeral=ephemeral,
            **DailyTaskEmbeds.job_embed(
                (
                    f"Scheduled `{job_type}` job `{created_job.id}` to run on "
                    f"`{schedule}`. (Cron: `{cron_expression}`)"
                ),
                ok=True,
            ),
            view=ScheduledJobActionView(
                job_id=str(created_job.id),
                channel_id=interaction.channel_id,
                guild_id=interaction.guild_id,
                response_ephemeral=ephemeral,
            ),
        )

    @tasks.loop(minutes=1)
    async def _runner(self) -> None:
        manager = DailyJobManager()
        try:
            due_jobs = await asyncio.to_thread(manager.get_due_jobs)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to load due scheduled jobs"
            )
            return

        if not due_jobs:
            return

        for job in due_jobs:
            try:
                payload = await asyncio.to_thread(job.run)
                await self._run_job(job, payload)
            except Exception:
                logging.getLogger(__name__).exception(
                    "Failed to process scheduled job",
                    extra={"job_id": str(job.id), "job_type": job.type},
                )
                await self._retry_one_time_job(job)

        try:
            await asyncio.to_thread(manager.fetch_jobs)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to refresh scheduled jobs after runner pass"
            )

    @staticmethod
    def _is_one_time_job(job: DailyJob) -> bool:
        schedule = job.schedule
        if isinstance(schedule, dict):
            return schedule.get("mode") == "one-time"
        return getattr(schedule, "mode", None) == "one-time"

    async def _retry_one_time_job(self, job: DailyJob) -> None:
        if not self._is_one_time_job(job) or job.last_run is None:
            return

        try:
            reset = await asyncio.to_thread(job.reset_run)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to restore one-time scheduled job for retry",
                extra={"job_id": str(job.id), "job_type": job.type},
            )
            return

        if reset:
            logging.getLogger(__name__).warning(
                "Restored one-time scheduled job for retry",
                extra={"job_id": str(job.id), "job_type": job.type},
            )

    @staticmethod
    def _has_sendable_payload(payload: Dict[str, Any]) -> bool:
        if str(payload.get("content") or "").strip():
            return True
        if payload.get("embed") is not None:
            return True
        if payload.get("embeds"):
            return True
        if payload.get("view") is not None:
            return True
        return False

    async def _run_job(self, job: DailyJob, payload: Dict[str, Any]) -> None:
        # Existing branches use `continue` as an early exit from this single-job pass.
        for _dispatch_once in (None,):
            if job.type == "pomodoro":
                channel = await resolve_messageable_channel(self.bot, job.channel_id)
                if channel is None:
                    raise ScheduledJobDeliveryUnavailable(
                        "Pomodoro destination is unavailable."
                    )
                data = job.data or {}
                mode = str(data.get("mode", "focus")).strip().lower()
                if mode not in ("focus", "break"):
                    mode = "focus"

                auto_cycle_enabled = PomodoroFunctions._is_truthy(
                    data.get("auto_cycle")
                )
                message_id_raw = str(data.get("message_id") or "").strip()
                user_raw = str(data.get("user") or "").strip()
                owner_id = int(user_raw) if user_raw.isdigit() else 0
                guild = getattr(channel, "guild", None)

                raw_focus_dur = str(data.get("focus_duration") or "").strip()
                raw_break_dur = str(data.get("break_duration") or "").strip()
                stored_focus_dur = int(raw_focus_dur) if raw_focus_dur.isdigit() else None
                stored_break_dur = int(raw_break_dur) if raw_break_dur.isdigit() else None
                current_streak = PomodoroFunctions._safe_int(
                    data.get("streak"), default=0
                )
                next_streak = PomodoroFunctions._next_streak(mode, current_streak)
                if mode == "focus" and owner_id:
                    await asyncio.to_thread(
                        PomodoroFunctions.update_best_pomodoro_streak,
                        owner_id,
                        next_streak,
                    )

                if auto_cycle_enabled:
                    next_mode = "break" if mode == "focus" else "focus"
                    next_duration_min = (
                        stored_break_dur if next_mode == "break" else stored_focus_dur
                    )
                    next_end_time, next_duration, next_data, next_schedule = (
                        PomodoroFunctions.insert_pomodoro_timer(
                            channel_id=job.channel_id or channel.id,
                            mode=next_mode,
                            duration_minutes=next_duration_min,
                            user_id=user_raw or owner_id,
                            break_duration=stored_break_dur,
                            focus_duration=stored_focus_dur,
                            streak=next_streak,
                        )
                    )
                    next_data["auto_cycle"] = True
                    if message_id_raw.isdigit():
                        next_data["message_id"] = message_id_raw

                    advanced = await asyncio.to_thread(
                        PomodoroFunctions.advance_auto_cycle_job,
                        job,
                        next_data,
                        next_schedule,
                    )
                    if not advanced:
                        raise ScheduledJobDeliveryUnavailable(
                            "Could not schedule the next pomodoro cycle."
                        )

                    join_url: Optional[str] = None
                    voice_error: Optional[str] = None
                    if guild is not None:
                        session = PomodoroVoiceManager.sessions.get(guild.id)
                        if session is not None:
                            voice_channel = guild.get_channel(session.voice_channel_id)
                            if isinstance(voice_channel, discord.VoiceChannel):
                                join_url = voice_channel.jump_url
                                voice_error = await PomodoroVoiceManager.start_session(
                                    guild,
                                    voice_channel,
                                    next_end_time,
                                    next_mode,
                                )

                    next_payload = PomodoroEmbeds.insert_timer_embed(
                        next_mode,
                        next_duration,
                        next_end_time,
                        focus_duration=stored_focus_dur,
                        break_duration=stored_break_dur,
                        streak=next_streak,
                    )
                    next_payload["view"] = PomodoroStartView(
                        owner_id,
                        join_url=join_url if voice_error is None else None,
                        mode=next_mode,
                        end_time=next_end_time,
                        auto_cycle_enabled=True,
                        voice_channel_select_enabled=guild is not None,
                        focus_duration=stored_focus_dur,
                        break_duration=stored_break_dur,
                        streak=next_streak,
                    )
                    next_payload["content"] = voice_error or None

                    notify_text = (
                        f"<@{owner_id}> Focus session finished."
                        if mode == "focus"
                        else f"<@{owner_id}> Break finished."
                    ) if owner_id else None
                    if notify_text:
                        await channel.send(content=notify_text)

                    posted_message: Optional[discord.Message] = None
                    if message_id_raw.isdigit():
                        try:
                            original_message = await channel.fetch_message(
                                int(message_id_raw)
                            )
                            await original_message.edit(**next_payload)
                            posted_message = original_message
                        except (
                            discord.NotFound,
                            discord.Forbidden,
                            discord.HTTPException,
                        ):
                            posted_message = await channel.send(**next_payload)
                    else:
                        posted_message = await channel.send(**next_payload)

                    if posted_message is not None and (
                        not message_id_raw.isdigit()
                        or posted_message.id != int(message_id_raw)
                    ):
                        await PomodoroFunctions.bind_timer_message(
                            job_id=str(job.id),
                            channel_id=job.channel_id,
                            guild_id=job.guild_id,
                            message_id=posted_message.id,
                        )
                    continue

                pomodoro_payload = PomodoroFunctions.pomodoro_payload(
                    job, streak=next_streak
                )
                chain_expires_at = datetime.datetime.now() + datetime.timedelta(
                    minutes=20
                )
                pomodoro_payload["view"] = PomodoroRestartView(
                    user_id=owner_id,
                    focus_duration=stored_focus_dur,
                    break_duration=stored_break_dur,
                    streak=next_streak,
                    chain_expires_at=chain_expires_at,
                )

                notify_text = pomodoro_payload.pop("content", None)
                end_time = PomodoroFunctions.parse_schedule_datetime(job.schedule)
                if guild is not None:
                    await PomodoroVoiceManager.stop_for_guild(guild.id, end_time)

                if notify_text:
                    await channel.send(content=notify_text)

                if not message_id_raw.isdigit():
                    await channel.send(**pomodoro_payload)
                    continue

                try:
                    original_message = await channel.fetch_message(int(message_id_raw))
                    await original_message.edit(**pomodoro_payload)
                except (
                    discord.NotFound,
                    discord.Forbidden,
                    discord.HTTPException,
                ):
                    await channel.send(**pomodoro_payload)
                continue
            if job.type == "todo":
                data = job.data or {}
                task_id = data.get("task_id")
                todo = TodoFunctions.fetch_todo(task_id, job.guild_id)
                if not todo or TodoFunctions.item_status(todo) == "done":
                    continue
                todo_list = None
                list_id = todo.get("list_id")
                if list_id:
                    try:
                        todo_list = await asyncio.to_thread(
                            TodoFunctions.fetch_todo_list_by_id,
                            list_id,
                        )
                    except Exception:
                        todo_list = None

                delivery = TodoFunctions.normalize_todo_reminder_delivery(
                    data.get("reminder_delivery")
                )
                created_by_user_id = self._coerce_int_id(
                    data.get("created_by_user_id")
                    or todo.get("created_by_user_id")
                    or todo.get("user_id")
                )
                assignee_id = TodoFunctions.item_assignee_id(todo)
                todo_scope = TodoFunctions._normalize_scope(str(todo.get("scope") or ""))

                dm_user_id: Optional[int] = None
                if delivery == "dm_assignee":
                    dm_user_id = assignee_id
                elif delivery == "dm_me" or (
                    delivery == "auto" and todo_scope == "personal"
                ):
                    dm_user_id = created_by_user_id or self._coerce_int_id(
                        todo.get("user_id")
                    )

                dm_delivery = delivery in {"dm_me", "dm_assignee"} or (
                    delivery == "auto" and todo_scope == "personal"
                )
                if dm_delivery:
                    user_id = dm_user_id
                    if not user_id:
                        logging.getLogger(__name__).warning(
                            "Skipping todo DM reminder without recipient",
                            extra={"job_id": str(job.id), "task_id": task_id},
                        )
                        raise ScheduledJobDeliveryUnavailable(
                            "Todo DM reminder has no recipient."
                        )
                    user = self.bot.get_user(user_id)
                    if user is None:
                        try:
                            user = await self.bot.fetch_user(user_id)
                        except (
                            discord.NotFound,
                            discord.Forbidden,
                            discord.HTTPException,
                        ):
                            logging.getLogger(__name__).exception(
                                "Failed to resolve todo reminder DM recipient",
                                extra={"user_id": user_id, "task_id": task_id},
                            )
                            raise ScheduledJobDeliveryUnavailable(
                                "Todo DM recipient is unavailable."
                            )
                    todo_payload = TodoEmbeds.todo_reminder_payload(
                        todo,
                        todo_list=todo_list,
                        mention_user_id=None,
                    )
                    try:
                        await user.send(**todo_payload)
                    except discord.HTTPException as exc:
                        logging.getLogger(__name__).exception(
                            "Failed to DM todo reminder",
                            extra={"user_id": user_id, "task_id": task_id},
                        )
                        raise ScheduledJobDeliveryUnavailable(
                            "Todo DM delivery failed."
                        ) from exc
                    continue

                channel_id = job.channel_id or self._coerce_int_id(
                    data.get("source_channel_id")
                )
                channel = await resolve_messageable_channel(self.bot, channel_id)
                if channel is None:
                    raise ScheduledJobDeliveryUnavailable(
                        "Todo reminder destination is unavailable."
                    )

                mention_user_id = created_by_user_id
                if (
                    delivery == "auto"
                    and "reminder_delivery" in data
                    and assignee_id is not None
                ):
                    mention_user_id = assignee_id
                todo_payload = TodoEmbeds.todo_reminder_payload(
                    todo,
                    todo_list=todo_list,
                    mention_user_id=mention_user_id,
                )
                await channel.send(**todo_payload)
                continue
            if job.type == "habit":
                habit_id = job.data.get("habit_id")
                habit = HabitFunctions.fetch_habit(habit_id, job.guild_id)
                if not habit:
                    continue
                if not HabitFunctions.needs_completion_today(habit):
                    continue

                if HabitFunctions._normalize_scope(str(habit.get("scope"))) == "personal":
                    user_id = habit.get("user_id")
                    if not user_id:
                        continue
                    user = self.bot.get_user(user_id)
                    if user is None:
                        try:
                            user = await self.bot.fetch_user(user_id)
                        except (
                            discord.NotFound,
                            discord.Forbidden,
                            discord.HTTPException,
                        ) as exc:
                            raise ScheduledJobDeliveryUnavailable(
                                "Habit DM recipient is unavailable."
                            ) from exc
                    habit_payload = HabitEmbeds.habit_reminder_payload(habit)
                    try:
                        await user.send(**habit_payload)
                    except discord.HTTPException as exc:
                        logging.getLogger(__name__).exception(
                            "Failed to DM habit reminder",
                            extra={"user_id": user_id, "habit_id": habit_id},
                        )
                        raise ScheduledJobDeliveryUnavailable(
                            "Habit DM delivery failed."
                        ) from exc
                    continue

                channel = await resolve_messageable_channel(self.bot, job.channel_id)
                if channel is None:
                    raise ScheduledJobDeliveryUnavailable(
                        "Habit reminder destination is unavailable."
                    )

                habit_payload = HabitEmbeds.habit_reminder_payload(habit)
                await channel.send(**habit_payload)
                continue
            if ReminderFunctions.is_reminder_job(job):
                channel = await resolve_reminder_destination(
                    self.bot,
                    channel_id=job.channel_id,
                    data=job.data,
                )
                if channel is None:
                    raise ScheduledJobDeliveryUnavailable(
                        "Reminder destination is unavailable."
                    )

                if job.type == "message":
                    reminder_guild = (
                        getattr(channel, "guild", None)
                        or (
                            self.bot.get_guild(job.guild_id)
                            if job.guild_id is not None
                            else None
                        )
                    )
                    reminder_view = ReminderOutputView(
                        job=job,
                        guild=reminder_guild,
                        result_message="Reminder triggered.",
                        ok=True,
                        user_id=(
                            ReminderFunctions.destination_user_id(job)
                            if ReminderFunctions.is_private_destination(job)
                            else None
                        ),
                        response_ephemeral=False,
                    )
                    reminder_payload = reminder_view.response_payload()
                    ping_text = ReminderFunctions.reminder_edit_values(job).get("ping_text")
                    if ping_text:
                        reminder_payload["content"] = ping_text

                    posted_message = await channel.send(**reminder_payload)
                    reminder_view.message = posted_message
                    await self._send_reminder_ping_dms(job)
                    continue

                if payload:
                    if not self._has_sendable_payload(payload):
                        logging.getLogger(__name__).error(
                            "Skipping reminder with an empty payload",
                            extra={"job_id": str(job.id), "job_type": job.type},
                        )
                        continue
                    await channel.send(**payload)
                    await self._send_reminder_ping_dms(
                        job,
                        message_payload=payload,
                    )
                continue
            if not payload:
                continue

            channel = await resolve_messageable_channel(self.bot, job.channel_id)
            if channel is None:
                raise ScheduledJobDeliveryUnavailable(
                    "Scheduled job destination is unavailable."
                )

            if not self._has_sendable_payload(payload):
                logging.getLogger(__name__).error(
                    "Skipping scheduled job with an empty payload",
                    extra={"job_id": str(job.id), "job_type": job.type},
                )
                continue

            await channel.send(**payload)

    @staticmethod
    def _truncate(text: str, limit: int = 60) -> str:
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    def _format_job(self, job: DailyJob) -> str:
        schedule_label = "unscheduled"
        schedule = job.schedule

        if isinstance(schedule, dict):
            mode = schedule.get("mode")
            if mode == "one-time":
                schedule_label = f"once at {schedule.get('datetime')}"
            elif mode == "cron":
                schedule_label = f"cron `{schedule.get('expression')}`"

        data_label = ""
        if job.type == "message":
            message = self._truncate(job.data.get("message", "").strip())
            data_label = f"message: {message}" if message else "message"
        elif job.type == "crypto":
            tickers = job.data.get("tickers", [])
            if isinstance(tickers, list):
                joined = ", ".join(tickers)
            else:
                joined = str(tickers)
            data_label = f"{job.type}: {joined}" if joined else job.type
        elif job.type == "stock":
            ticker = (job.data.get("ticker") or "").strip()
            data_label = f"stock: {ticker}" if ticker else "stock"
        else:
            data_label = job.type

        return f"- `{job.id}` {data_label} ({schedule_label})"

    if not settings.jobs_commands_disabled:
        @jobs.command(name="list", description="List scheduled jobs for this channel")
        @app_commands.describe(visibility=VISIBILITY_DESC)
        @app_commands.choices(visibility=VISIBILITY_CHOICES)
        async def jobs_list(
            self,
            interaction: discord.Interaction,
            visibility: Optional[app_commands.Choice[str]] = None,
        ) -> None:
            ephemeral = self._resolve_response_visibility(interaction, visibility)
            await interaction.response.defer(ephemeral=ephemeral)
            manager = DailyJobManager()
            jobs = await asyncio.to_thread(
                manager.list_jobs,
                interaction.channel_id,
                interaction.guild_id,
            )

            lines = [self._format_job(job) for job in jobs]
            await interaction.followup.send(
                ephemeral=ephemeral, **DailyTaskEmbeds.jobs_list_embed(lines)
            )

        @jobs.command(name="delete", description="Delete a scheduled job")
        @app_commands.describe(
            job_id="Job id from /jobs list",
            visibility=VISIBILITY_DESC,
        )
        @app_commands.choices(visibility=VISIBILITY_CHOICES)
        async def jobs_cancel(
            self,
            interaction: discord.Interaction,
            job_id: str,
            visibility: Optional[app_commands.Choice[str]] = None,
        ) -> None:
            ephemeral = self._resolve_response_visibility(interaction, visibility)
            await interaction.response.defer(ephemeral=ephemeral)
            manager = DailyJobManager()

            try:
                deleted = await asyncio.to_thread(
                    manager.delete_job,
                    job_id.strip(),
                    interaction.channel_id,
                    interaction.guild_id,
                )
            except ValueError as exc:
                raise ValidationError(
                    "That job id is invalid.",
                    ephemeral=ephemeral,
                    cause=exc,
                )

            if deleted:
                await interaction.followup.send(
                    ephemeral=ephemeral,
                    **DailyTaskEmbeds.jobs_cancel_embed(
                        f"Deleted job `{job_id}`.", ok=True
                    ),
                )
                return

            raise ValidationError(
                "No job found with that id in this channel.",
                ephemeral=ephemeral,
            )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(DailyTaskCog(client))
