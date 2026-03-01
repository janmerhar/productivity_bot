import asyncio
import logging
import datetime
import json
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import discord
import dateparser
from discord import app_commands
from discord.ext import commands, tasks

from classes.DailyJob import CronSchedule, DailyJob, OneTimeSchedule2
from classes.DailyJobManager import DailyJobManager
from classes.PomodoroFunctions import PomodoroFunctions
from classes.TodoFunctions import TodoFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from embeds.HabitEmbeds import HabitEmbeds
from embeds.TodoEmbeds import TodoEmbeds
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from views.PomodoroRestartView import PomodoroRestartView
from classes.HabitFunctions import HabitFunctions
from services.discord_helpers import resolve_messageable_channel
from services.cron_schedule import (
    CronConversionError,
    is_valid_cron_expression,
    resolve_cron_expression,
)
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


def parse_time_string(
    raw: str,
    timezone: Optional[str] = None,
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
        if dt <= now:
            dt += datetime.timedelta(days=1)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt

    return None


class DailyTaskCog(commands.Cog):
    jobs = app_commands.Group(name="jobs", description="Manage scheduled jobs")
    reminder_group = app_commands.Group(
        name="reminder", description="Manage one-time reminders"
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._runner.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print("DailyTaskCog cog loaded")

    def cog_unload(self) -> None:
        if self._runner.is_running():
            self._runner.cancel()

    @reminder_group.command(
        name="create", description="Create a one time reminder"
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder(
        self,
        interaction: discord.Interaction,
        time: str,
        message: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        async def _continue_with_timezone(
            followup_interaction: discord.Interaction,
            resolved_timezone: str,
        ) -> None:
            await self._create_reminder(
                interaction=followup_interaction,
                time=time,
                message=message,
                ephemeral=ephemeral,
                timezone=resolved_timezone,
            )

        timezone = await ensure_user_timezone(
            interaction,
            _continue_with_timezone,
            continue_message="Timezone saved as `{timezone}`. Continuing `/reminder create`.",
        )
        if timezone is None:
            return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._create_reminder(
            interaction=interaction,
            time=time,
            message=message,
            ephemeral=ephemeral,
            timezone=timezone,
        )

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
        ephemeral = resolve_visibility(visibility, default="private")
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

    async def _create_reminder(
        self,
        interaction: discord.Interaction,
        time: str,
        message: str,
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        scheduled_dt = parse_time_string(time, timezone=timezone)
        if scheduled_dt is None:
            raise ValidationError(
                "I couldn't understand that time.",
                hint="Try '08:30', '8pm', or similar.",
                ephemeral=ephemeral,
            )

        job_schedule = OneTimeSchedule2(datetime=scheduled_dt.isoformat())
        payload = message.strip()
        job_type = "message"
        job_data = {"message": message}
        confirmation_time = scheduled_dt.strftime("%H:%M")
        confirmation = f"Got it! I'll post here at {confirmation_time}."

        if payload.lower().startswith("stock:"):
            stock_value = payload[6:].strip()
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

            job_type = "stock"
            symbol = stock_tokens[0]
            job_data = {"ticker": symbol}
            confirmation = (
                f"Got it! I'll post daily stock price for `{symbol}` at "
                f"{confirmation_time}."
            )

        manager = DailyJobManager()
        try:
            await asyncio.to_thread(
                manager.insert_job,
                interaction.guild_id,
                interaction.channel_id,
                job_type,
                job_data,
                job_schedule,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while scheduling that task. Please try again.",
                ephemeral=ephemeral,
                cause=exc,
            )
        await interaction.followup.send(
            ephemeral=ephemeral, **DailyTaskEmbeds.reminder_embed(confirmation, ok=True)
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
        schedule_config = CronSchedule(expression=cron_expression)

        try:
            await asyncio.to_thread(
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
                    f"Scheduled `{job_type}` job to run on `{schedule}`. "
                    f"(Cron: `{cron_expression}`)"
                ),
                ok=True,
            ),
        )

    @tasks.loop(minutes=1)
    async def _runner(self) -> None:
        manager = DailyJobManager()
        manager.get_due_jobs()
        runs = await asyncio.to_thread(manager.run_due_jobs)

        if not runs:
            return

        for job, payload in runs:
            if job.type == "pomodoro":
                channel = await resolve_messageable_channel(self.bot, job.channel_id)
                if channel is None:
                    continue
                pomodoro_payload = PomodoroFunctions.pomodoro_payload(job)
                pomodoro_payload["view"] = PomodoroRestartView()
                await channel.send(**pomodoro_payload)

                end_time = PomodoroFunctions.parse_schedule_datetime(job.schedule)
                guild = getattr(channel, "guild", None)
                await PomodoroVoiceManager.stop_for_guild(guild.id, end_time)
                continue
            if job.type == "todo":
                task_id = job.data.get("task_id")
                todo = TodoFunctions.fetch_todo(task_id, job.guild_id)
                if not todo or todo.get("state") != "todo":
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
                if todo.get("scope") == "personal":
                    user_id = todo.get("user_id")
                    if not user_id:
                        continue
                    user = self.bot.get_user(user_id)
                    if user is None:
                        user = await self.bot.fetch_user(user_id)
                    todo_payload = TodoEmbeds.todo_reminder_payload(
                        todo,
                        todo_list=todo_list,
                    )
                    try:
                        await user.send(**todo_payload)
                    except discord.HTTPException:
                        logging.getLogger(__name__).exception(
                            "Failed to DM todo reminder",
                            extra={"user_id": user_id, "task_id": task_id},
                        )
                    continue

                channel = await resolve_messageable_channel(self.bot, job.channel_id)
                if channel is None:
                    continue

                todo_payload = TodoEmbeds.todo_reminder_payload(
                    todo,
                    todo_list=todo_list,
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

                channel = await resolve_messageable_channel(self.bot, job.channel_id)
                if channel is None:
                    continue

                habit_payload = HabitEmbeds.habit_reminder_payload(habit)
                await channel.send(**habit_payload)
                continue
            if not payload:
                continue

            channel = await resolve_messageable_channel(self.bot, job.channel_id)
            if channel is None:
                continue

            await channel.send(**payload)

    @_runner.before_loop
    async def _before_runner(self) -> None:
        await self.bot.wait_until_ready()

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

    @jobs.command(name="list", description="List scheduled jobs for this channel")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def jobs_list(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
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
        ephemeral = resolve_visibility(visibility, default="private")
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
