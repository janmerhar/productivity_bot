import asyncio
import datetime
from typing import Optional

import discord

from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from services.discord_helpers import format_reminder_mentions
from services.error_reporting import ValidationError, handle_interaction_error


class ReminderDeleteConfirmModal(discord.ui.Modal):
    def __init__(self, parent_view: "ReminderOutputView") -> None:
        super().__init__(title="Delete Reminder")
        self.parent_view = parent_view
        reminder_name = "this reminder"
        if parent_view.job is not None:
            label = str(ReminderFunctions.reminder_label(parent_view.job) or "").strip()
            if label:
                reminder_name = f"`{label[:80]}`"
        self.add_item(
            discord.ui.TextDisplay(
                f"This will permanently delete {reminder_name} (`{parent_view.job_id}`)."
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.parent_view._confirm_delete(interaction)


class ReminderOutputView(discord.ui.View):
    def __init__(
        self,
        *,
        job: Optional[DailyJob],
        guild: Optional[discord.Guild],
        result_message: str,
        ok: bool = True,
        user_id: Optional[int] = None,
        response_ephemeral: bool = False,
        job_id: Optional[str] = None,
        guild_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.job: Optional[DailyJob] = job
        self.guild = guild
        self.result_message = result_message
        self.ok = bool(ok)
        self.user_id = user_id
        self.response_ephemeral = bool(response_ephemeral)
        self.message: Optional[discord.Message] = None

        resolved_job_id = str(job.id) if job is not None else str(job_id or "").strip()
        if not resolved_job_id:
            raise ValueError("ReminderOutputView needs a reminder id.")

        self.job_id = resolved_job_id
        self.guild_id = job.guild_id if job is not None else guild_id
        self.channel_id = job.channel_id if job is not None else channel_id
        self._rebuild_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id is None or interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "Only the user who opened this reminder can manage it.",
            ephemeral=self.response_ephemeral,
        )
        return False

    async def refresh_state(self) -> None:
        self.job = await asyncio.to_thread(
            ReminderFunctions.get_reminder,
            self.job_id,
            self.guild_id,
        )
        if self.job is not None:
            self.channel_id = self.job.channel_id
        self._rebuild_items()

    async def refresh_message(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message] = None,
        jump_to_last_page: bool = False,
        result_message: Optional[str] = None,
    ) -> bool:
        del jump_to_last_page
        if result_message is not None:
            self.result_message = result_message

        await self.refresh_state()
        candidates = []
        for candidate in (source_message, interaction.message, self.message):
            if candidate is None:
                continue
            if any(
                getattr(existing, "id", None) == getattr(candidate, "id", None)
                for existing in candidates
            ):
                continue
            candidates.append(candidate)

        payload = self.response_payload()
        for candidate in candidates:
            try:
                await candidate.edit(**payload)
                self.message = candidate
                return True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue

        source_message_id = getattr(source_message, "id", None)
        if source_message_id is not None:
            try:
                await interaction.followup.edit_message(
                    source_message_id,
                    **payload,
                )
                self.message = source_message
                return True
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

        return False

    def _rebuild_items(self) -> None:
        from views.reminder_dynamic_items import (
            ReminderDeleteButton,
            ReminderDuplicateButton,
            ReminderEditButton,
            ReminderPingButton,
            ReminderToggleButton,
        )

        self.clear_items()
        has_job = self.job is not None
        encoded_user_id = int(self.user_id or 0)
        is_paused = has_job and ReminderFunctions.is_paused(self.job)

        self.add_item(
            ReminderToggleButton(
                self.job_id,
                encoded_user_id,
                self.response_ephemeral,
                paused=bool(is_paused),
                disabled=not has_job,
            )
        )
        self.add_item(
            ReminderEditButton(
                self.job_id,
                encoded_user_id,
                self.response_ephemeral,
                disabled=not has_job,
            )
        )
        self.add_item(
            ReminderPingButton(
                self.job_id,
                encoded_user_id,
                self.response_ephemeral,
                disabled=not has_job,
            )
        )
        self.add_item(
            ReminderDuplicateButton(
                self.job_id,
                encoded_user_id,
                self.response_ephemeral,
                disabled=not has_job,
            )
        )
        self.add_item(
            ReminderDeleteButton(
                self.job_id,
                encoded_user_id,
                self.response_ephemeral,
                disabled=not has_job,
            )
        )

    @staticmethod
    def _cron_human_label(expression: str) -> str:
        try:
            from cron_descriptor import get_description
            return get_description(expression.strip())
        except Exception:
            return expression

    @staticmethod
    def _cron_next_run(expression: str) -> Optional[str]:
        try:
            from croniter import croniter
            it = croniter(expression, datetime.datetime.now())
            next_dt = it.get_next(datetime.datetime)
            return f"<t:{int(next_dt.timestamp())}:R>"
        except Exception:
            return None

    @staticmethod
    def _format_channel(job: Optional[DailyJob], channel_id: Optional[int]) -> str:
        if job is not None:
            return ReminderFunctions.destination_label(job)
        if channel_id is None:
            return "unknown"
        return f"<#{channel_id}>"

    @staticmethod
    def _format_timestamp(raw_value: str) -> Optional[str]:
        text = str(raw_value or "").strip()
        if not text:
            return None
        try:
            scheduled_at = datetime.datetime.fromisoformat(text)
        except ValueError:
            try:
                scheduled_at = datetime.datetime.strptime(text, "%Y-%m-%d %H:%M")
            except ValueError:
                scheduled_at = None
        if scheduled_at is None:
            return f"`{text}`"
        return f"<t:{int(scheduled_at.timestamp())}:f> (<t:{int(scheduled_at.timestamp())}:R>)"

    def _schedule_value(self) -> str:
        if self.job is None:
            return "unknown"

        schedule = self.job.schedule
        if isinstance(schedule, dict):
            mode = str(schedule.get("mode") or "").strip().lower()
            raw_datetime = str(schedule.get("datetime") or "").strip()
        else:
            mode = str(getattr(schedule, "mode", "") or "").strip().lower()
            raw_datetime = str(getattr(schedule, "datetime", "") or "").strip()

        schedule_text = str(
            ReminderFunctions.reminder_edit_values(self.job).get("schedule") or ""
        ).strip()

        if mode == "one-time":
            formatted = self._format_timestamp(raw_datetime)
            return f"📅 {formatted}" if formatted else (f"📅 {schedule_text}" if schedule_text else "unknown")

        if schedule_text:
            human = self._cron_human_label(schedule_text)
            next_run = self._cron_next_run(schedule_text)
            return f"🔁 {human}\nNext: {next_run}" if next_run else f"🔁 {human}"

        return "unknown"

    def _pause_until_value(self) -> Optional[str]:
        if self.job is None or not ReminderFunctions.is_paused(self.job):
            return None

        pause_until = ReminderFunctions.pause_until_for_job(self.job)
        if pause_until is None:
            return None

        return self._format_timestamp(pause_until.isoformat())

    def _embed(self) -> discord.Embed:
        if self.job is None:
            embed = discord.Embed(
                title="Reminder",
                description=self.result_message,
                color=discord.Colour.red() if not self.ok else discord.Colour.blurple(),
            )
            embed.set_author(name="🔔 Reminder")
            embed.add_field(name="ID", value=f"`{self.job_id}`", inline=True)
            embed.add_field(name="Status", value="missing", inline=True)
            embed.add_field(
                name="Destination",
                value=self._format_channel(self.job, self.channel_id),
                inline=True,
            )
            embed.add_field(
                name="Details",
                value="This reminder is no longer available.",
                inline=False,
            )
            return embed

        values = ReminderFunctions.reminder_edit_values(self.job)
        reminder_name = str(values.get("reminder") or "Untitled reminder").strip()
        is_paused = ReminderFunctions.is_paused(self.job)

        if not self.ok:
            color = discord.Colour.red()
        elif is_paused:
            color = discord.Colour.gold()
        else:
            color = discord.Colour.green()

        embed = discord.Embed(
            title=reminder_name[:256],
            description=self.result_message or None,
            color=color,
        )
        embed.set_author(name="🔔 Reminder")

        status_value = "⏸️ Paused" if is_paused else "🟢 Active"
        embed.add_field(
            name="Destination",
            value=self._format_channel(self.job, self.channel_id),
            inline=True,
        )
        embed.add_field(name="Status", value=status_value, inline=True)

        pause_until_value = self._pause_until_value()
        if pause_until_value:
            embed.add_field(name="Paused Until", value=pause_until_value, inline=False)

        embed.add_field(name="Schedule", value=self._schedule_value(), inline=False)

        ping_value = format_reminder_mentions(self.guild, values.get("ping_text"))
        if ping_value:
            embed.add_field(name="Ping", value=ping_value[:1024], inline=False)
            if ReminderFunctions.notify_ping_users_in_dm(self.job):
                embed.add_field(name="Ping DMs", value="Enabled", inline=True)

        description_value = str(values.get("description") or "").strip()
        if description_value:
            embed.add_field(
                name="Description", value=description_value[:1024], inline=False
            )

        thumbnail_value = str(values.get("thumbnail_url") or "").strip()
        if thumbnail_value:
            embed.set_thumbnail(url=thumbnail_value)

        expires_value = self._format_timestamp(
            values.get("expires") or values.get("until") or ""
        )
        if expires_value:
            embed.add_field(name="Expires", value=expires_value, inline=False)

        return embed

    def payload(self) -> dict:
        return {"embed": self._embed()}

    def response_payload(self) -> dict:
        payload = self.payload()
        if self.children:
            payload["view"] = self
        return payload

    async def _confirm_delete(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=self.response_ephemeral)
        try:
            deleted = await asyncio.to_thread(
                ReminderFunctions.delete_reminder,
                self.job_id,
                self.guild_id,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That reminder ID is invalid.",
                    ephemeral=self.response_ephemeral,
                    cause=exc,
                ),
                ephemeral=self.response_ephemeral,
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )
            return

        if not deleted:
            self.job = None
            self.ok = False
            self.result_message = "This reminder is no longer available."
            self._rebuild_items()
            await self.refresh_message(
                interaction,
                source_message=interaction.message,
                result_message=self.result_message,
            )
            await interaction.followup.send(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        self.job = None
        self.ok = True
        self.result_message = f"Deleted reminder `{self.job_id}`."
        self._rebuild_items()
        await self.refresh_message(
            interaction,
            source_message=interaction.message,
            result_message=self.result_message,
        )
