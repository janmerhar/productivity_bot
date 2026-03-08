import asyncio
import datetime
import math
from typing import List, Optional

import discord

from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from views.ReminderEditModal import ReminderCreateModal


class ReminderListView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(
        self,
        *,
        reminders: List[DailyJob],
        scope_label: str,
        status_label: str,
        guild_id: Optional[int],
        channel_id: Optional[int],
        paused_filter: Optional[bool],
        user_id: Optional[int],
        response_ephemeral: bool = False,
        page: int = 1,
        timeout: float = 300,
    ) -> None:
        super().__init__(timeout=timeout)
        self.reminders = reminders
        self.scope_label = scope_label
        self.status_label = status_label
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.paused_filter = paused_filter
        self.user_id = user_id
        self.response_ephemeral = bool(response_ephemeral)
        self.page_size = self.PAGE_SIZE
        self.total_pages = max(1, math.ceil(len(self.reminders) / self.page_size))
        self.page = max(1, min(page, self.total_pages))
        self._sync_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id is None or interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "Only the user who opened this reminder list can change pages.",
            ephemeral=self.response_ephemeral,
        )
        return False

    def _page_slice(self) -> List[DailyJob]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.reminders[start:end]

    @staticmethod
    def _truncate(text: str, limit: int = 80) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3].rstrip()}..."

    @staticmethod
    def _destination_label(job: DailyJob) -> str:
        if job.channel_id is None:
            return "unknown"
        return f"<#{job.channel_id}>"

    @staticmethod
    def _datetime_label(raw_value: str) -> Optional[str]:
        text = str(raw_value or "").strip()
        if not text:
            return None
        try:
            scheduled_at = datetime.datetime.fromisoformat(text)
        except ValueError:
            return f"`{ReminderListView._truncate(text, 48)}`"
        timestamp = int(scheduled_at.timestamp())
        return f"<t:{timestamp}:f> (<t:{timestamp}:R>)"

    @staticmethod
    def _schedule_label(job: DailyJob) -> str:
        schedule = job.schedule
        if isinstance(schedule, dict):
            mode = str(schedule.get("mode") or "").strip().lower()
            expression = str(schedule.get("expression") or "").strip()
            raw_datetime = str(schedule.get("datetime") or "").strip()
        else:
            mode = str(getattr(schedule, "mode", "") or "").strip().lower()
            expression = str(getattr(schedule, "expression", "") or "").strip()
            raw_datetime = str(getattr(schedule, "datetime", "") or "").strip()

        if mode == "one-time":
            formatted = ReminderListView._datetime_label(raw_datetime)
            return formatted or "`unscheduled`"

        if mode == "cron":
            return f"`{ReminderListView._truncate(expression or 'cron', 48)}`"

        raw_value = ReminderFunctions.schedule_input_for_job(job)
        return f"`{ReminderListView._truncate(raw_value or 'unscheduled', 48)}`"

    @staticmethod
    def _expires_label(job: DailyJob) -> Optional[str]:
        raw_value = str((job.data or {}).get("expires_at") or "").strip()
        return ReminderListView._datetime_label(raw_value)

    def _embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Reminder List",
            color=discord.Colour.blurple(),
        )

        page_items = self._page_slice()
        if not page_items:
            embed.description = "No reminders found."
            embed.set_footer(
                text=(
                    f"Page {self.page}/{self.total_pages} | Items: {len(self.reminders)} | "
                    f"Scope: {self.scope_label} | Status: {self.status_label}"
                )
            )
            return embed

        for display_index, job in enumerate(page_items, start=1):
            label = self._truncate(ReminderFunctions.reminder_label(job), 90)
            status = "paused" if ReminderFunctions.is_paused(job) else "active"
            value_lines = [
                f"Schedule: {self._schedule_label(job)}",
                f"Channel: {self._destination_label(job)} | ID: `{str(job.id)[:8]}`",
            ]
            expires_label = self._expires_label(job)
            if expires_label:
                value_lines.append(f"Expires: {expires_label}")
            embed.add_field(
                name=f"{display_index}. {label} [{status}]",
                value="\n".join(value_lines),
                inline=False,
            )

        embed.set_footer(
            text=(
                f"Page {self.page}/{self.total_pages} | Items: {len(self.reminders)} | "
                f"Scope: {self.scope_label} | Status: {self.status_label}"
            )
        )
        return embed

    def payload(self) -> dict:
        return {"embed": self._embed()}

    async def _reload_reminders(self) -> None:
        self.reminders = await asyncio.to_thread(
            ReminderFunctions.list_reminders,
            self.guild_id,
            self.paused_filter,
            self.channel_id,
        )
        self.total_pages = max(1, math.ceil(len(self.reminders) / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))

    async def refresh_message(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message] = None,
        jump_to_last_page: bool = False,
    ) -> None:
        await self._reload_reminders()
        if jump_to_last_page and self.reminders:
            self.page = self.total_pages
        self._sync_buttons()

        target_message = source_message or interaction.message
        if target_message is None:
            return

        try:
            await target_message.edit(view=self, **self.payload())
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(
                "Reminder created, but the original list message is no longer available.",
                ephemeral=self.response_ephemeral,
            )

    def _sync_buttons(self) -> None:
        self.previous_page.disabled = self.page <= 1
        self.next_page.disabled = self.page >= self.total_pages

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, row=0)
    async def previous_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        if self.page <= 1:
            await interaction.response.defer()
            return
        self.page -= 1
        self._sync_buttons()
        await interaction.response.edit_message(view=self, **self.payload())

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=0)
    async def next_page(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        if self.page >= self.total_pages:
            await interaction.response.defer()
            return
        self.page += 1
        self._sync_buttons()
        await interaction.response.edit_message(view=self, **self.payload())

    @discord.ui.button(
        label="New Reminder",
        style=discord.ButtonStyle.primary,
        row=1,
    )
    async def create_reminder(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        default_channel_id = self.channel_id or interaction.channel_id
        await interaction.response.send_modal(
            ReminderCreateModal(
                parent_view=self,
                default_channel_id=default_channel_id,
                source_message=interaction.message,
                response_ephemeral=self.response_ephemeral,
            )
        )
