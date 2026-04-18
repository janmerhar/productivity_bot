import asyncio
import logging
import json
from typing import Any, Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from classes.DailyJob import CronSchedule, DailyJob
from classes.DailyJobManager import DailyJobManager
from classes.PomodoroFunctions import PomodoroFunctions
from classes.ReminderFunctions import ReminderFunctions
from classes.TodoFunctions import TodoFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from embeds.HabitEmbeds import HabitEmbeds
from embeds.TodoEmbeds import TodoEmbeds
from classes.PomodoroVoiceManager import PomodoroVoiceManager
from views.PomodoroRestartView import PomodoroRestartView
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
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility
from views.ReminderOutputView import ReminderOutputView


class DailyTaskCog(commands.Cog):
    jobs = app_commands.Group(name="jobs", description="Manage scheduled jobs")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._runner.start()

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

    def cog_unload(self) -> None:
        if self._runner.is_running():
            self._runner.cancel()

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
            if ReminderFunctions.is_reminder_job(job):
                channel = await resolve_reminder_destination(
                    self.bot,
                    channel_id=job.channel_id,
                    data=job.data,
                )
                if channel is None:
                    continue

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
