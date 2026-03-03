import asyncio
import datetime
import math
from typing import Any, Dict, List, Optional, Tuple

import discord

from classes.DailyJobManager import DailyJobManager
from classes.PriceAlertFunctions import deactivate_alert, fetch_user_active_alerts
from services.error_reporting import handle_interaction_error
from views.ScheduledJobActionView import ScheduledJobActionView


class StockListItemsView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(
        self,
        user_id: int,
        guild_id: Optional[int],
        channel_id: Optional[int],
        kind: str = "all",
        timeout: float = 900,
    ) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.kind = kind if kind in {"all", "schedules", "alerts"} else "all"

        self.entries: List[Dict[str, Any]] = []
        self.schedule_count = 0
        self.alert_count = 0

        self.page = 1
        self.total_pages = 1
        self.selected_index = 0

    async def initialize(self) -> None:
        await self._reload_entries()
        self._sync_button_state()

    @staticmethod
    def _entry_key(entry: Dict[str, Any]) -> Tuple[str, str]:
        entry_type = str(entry.get("entry_type") or "")
        if entry_type == "schedule":
            return entry_type, str(entry.get("job_id") or "")
        return entry_type, str(entry.get("alert_id") or "")

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3]}..."

    @staticmethod
    def _parse_expires(expires_at: Any) -> str:
        if isinstance(expires_at, datetime.datetime):
            return f"<t:{int(expires_at.timestamp())}:R>"
        return "none"

    @staticmethod
    def _schedule_core(schedule: Dict[str, Any]) -> str:
        mode = str((schedule or {}).get("mode") or "")
        if mode == "cron":
            expression = str(schedule.get("expression") or "").strip()
            return f"cron {expression}" if expression else "cron"
        if mode == "one-time":
            dt_value = str(schedule.get("datetime") or "").strip()
            return f"once {dt_value}" if dt_value else "once"
        return "unscheduled"

    @staticmethod
    def _target_price_label(value: Any, currency: str) -> str:
        try:
            parsed = float(value)
            formatted = f"{parsed:,.2f}"
        except (TypeError, ValueError):
            formatted = "unknown"
        return f"{formatted}{f' {currency}' if currency else ''}"

    @staticmethod
    def _id_short(raw_value: str) -> str:
        value = str(raw_value or "").strip()
        if len(value) <= 8:
            return value or "unknown"
        return value[:8]

    async def _reload_entries(self) -> None:
        previous_key: Optional[Tuple[str, str]] = None
        if self.entries and 0 <= self.selected_index < len(self.entries):
            previous_key = self._entry_key(self.entries[self.selected_index])

        schedules: List[Dict[str, Any]] = []
        alerts: List[Dict[str, Any]] = []

        if self.kind in {"all", "schedules"}:
            manager = DailyJobManager()
            jobs = await asyncio.to_thread(
                manager.list_jobs,
                self.channel_id,
                self.guild_id,
            )
            stock_jobs = [job for job in jobs if job.type == "stock"]
            stock_jobs.sort(key=lambda job: str(job.id))

            schedules = [
                {
                    "entry_type": "schedule",
                    "job_id": str(job.id),
                    "ticker": str((job.data or {}).get("ticker") or "").strip().upper(),
                    "header": str((job.data or {}).get("header") or "").strip(),
                    "schedule": job.schedule or {},
                    "channel_id": job.channel_id,
                    "guild_id": job.guild_id,
                }
                for job in stock_jobs
            ]

        if self.kind in {"all", "alerts"}:
            alerts_raw = await asyncio.to_thread(
                fetch_user_active_alerts,
                "stock",
                self.user_id,
                self.guild_id,
                100,
            )
            alerts = [
                {
                    "entry_type": "alert",
                    "alert_id": str(item.get("_id") or ""),
                    "symbol": str(item.get("symbol") or "").strip().upper(),
                    "condition": str(item.get("condition") or "above").strip().lower(),
                    "target_price": item.get("target_price"),
                    "currency": str(item.get("currency") or "").strip().upper(),
                    "destination_type": str(item.get("destination_type") or "channel"),
                    "channel_id": item.get("channel_id"),
                    "expires_at": item.get("expires_at"),
                }
                for item in alerts_raw
            ]

        self.schedule_count = len(schedules)
        self.alert_count = len(alerts)

        if self.kind == "schedules":
            self.entries = schedules
        elif self.kind == "alerts":
            self.entries = alerts
        else:
            self.entries = schedules + alerts

        if not self.entries:
            self.selected_index = 0
            self.page = 1
            self.total_pages = 1
            return

        selected_index = None
        if previous_key is not None:
            for idx, entry in enumerate(self.entries):
                if self._entry_key(entry) == previous_key:
                    selected_index = idx
                    break

        if selected_index is None:
            selected_index = max(0, min(self.selected_index, len(self.entries) - 1))

        self.selected_index = selected_index
        self.total_pages = max(1, math.ceil(len(self.entries) / self.PAGE_SIZE))
        self.page = (self.selected_index // self.PAGE_SIZE) + 1

    def _summary_text(self) -> str:
        scope_line = "Schedules are scoped to this channel."
        if self.guild_id is None:
            alerts_line = "Alerts show your active stock alerts across servers and DMs."
        else:
            alerts_line = "Alerts show your active stock alerts in this server."
        return (
            f"{scope_line}\n"
            f"{alerts_line}\n"
            f"Showing up to {self.PAGE_SIZE} items per page.\n"
            f"Schedules: **{self.schedule_count}** | Alerts: **{self.alert_count}**"
        )

    def _page_slice(self) -> List[Dict[str, Any]]:
        start = (self.page - 1) * self.PAGE_SIZE
        end = start + self.PAGE_SIZE
        return self.entries[start:end]

    def _selected_entry(self) -> Optional[Dict[str, Any]]:
        if not self.entries:
            return None
        if self.selected_index < 0 or self.selected_index >= len(self.entries):
            return None
        return self.entries[self.selected_index]

    def _schedule_line(
        self, display_index: int, entry: Dict[str, Any], selected: bool
    ) -> str:
        ticker = self._truncate(str(entry.get("ticker") or "UNKNOWN"), 10)
        schedule_value = self._truncate(
            self._schedule_core(entry.get("schedule") or {}),
            28,
        )
        channel_id = entry.get("channel_id")
        channel_value = f"<#{channel_id}>" if channel_id else "unknown"
        header = self._truncate(str(entry.get("header") or "-"), 20) or "-"
        job_id = self._id_short(str(entry.get("job_id") or ""))
        marker = ">" if selected else " "
        return (
            f"{marker}{display_index}. SCH | {ticker} | {schedule_value} | "
            f"{channel_value} | {header} | {job_id}"
        )

    def _alert_line(
        self, display_index: int, entry: Dict[str, Any], selected: bool
    ) -> str:
        symbol = self._truncate(str(entry.get("symbol") or "UNKNOWN"), 10)
        trigger = self._truncate(
            (
                f"{str(entry.get('condition') or 'above').strip().lower()} "
                f"{self._target_price_label(entry.get('target_price'), str(entry.get('currency') or '').strip().upper())}"
            ),
            24,
        )
        destination_type = (
            str(entry.get("destination_type") or "channel").strip().lower()
        )
        channel_id = entry.get("channel_id")
        destination = (
            "DM"
            if destination_type == "dm"
            else (f"<#{channel_id}>" if channel_id else "channel")
        )
        expires = self._truncate(self._parse_expires(entry.get("expires_at")), 15)
        alert_id = self._id_short(str(entry.get("alert_id") or ""))
        marker = ">" if selected else " "
        return (
            f"{marker}{display_index}. ALR | {symbol} | {trigger} | "
            f"{destination} | {expires} | {alert_id}"
        )

    def _selected_details(self, entry: Dict[str, Any]) -> str:
        entry_type = str(entry.get("entry_type") or "")
        if entry_type == "schedule":
            return (
                f"Type: schedule\n"
                f"ID: `{str(entry.get('job_id') or 'unknown')}`\n"
                f"Ticker: `{str(entry.get('ticker') or 'UNKNOWN')}`\n"
                f"Schedule: {self._schedule_core(entry.get('schedule') or {})}\n"
                f"Header: {str(entry.get('header') or '-')}"
            )
        target_label = self._target_price_label(
            entry.get("target_price"),
            str(entry.get("currency") or "").strip().upper(),
        )
        destination_type = (
            str(entry.get("destination_type") or "channel").strip().lower()
        )
        channel_id = entry.get("channel_id")
        destination = (
            "DM"
            if destination_type == "dm"
            else (f"<#{channel_id}>" if channel_id else "channel")
        )
        return (
            f"Type: alert\n"
            f"ID: `{str(entry.get('alert_id') or 'unknown')}`\n"
            f"Symbol: `{str(entry.get('symbol') or 'UNKNOWN')}`\n"
            f"Trigger: `{str(entry.get('condition') or 'above')}` `{target_label}`\n"
            f"Destination: {destination}\n"
            f"Expires: {self._parse_expires(entry.get('expires_at'))}"
        )

    def payload(self) -> dict:
        embed = discord.Embed(
            title="Stock Tracking",
            color=discord.Colour.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        embed.description = self._summary_text()

        if not self.entries:
            embed.add_field(
                name="No items",
                value="No matching stock schedules or alerts found.",
                inline=False,
            )
            return {"embed": embed}

        page_entries = self._page_slice()
        page_start = (self.page - 1) * self.PAGE_SIZE
        lines: List[str] = []
        for local_idx, entry in enumerate(page_entries):
            absolute_index = page_start + local_idx
            display_index = local_idx + 1
            selected = absolute_index == self.selected_index
            if str(entry.get("entry_type") or "") == "schedule":
                line = self._schedule_line(display_index, entry, selected)
            else:
                line = self._alert_line(display_index, entry, selected)
            lines.append(line)

        embed.add_field(
            name=f"Items (page {self.page}/{self.total_pages})",
            value="\n".join(lines)[:1024],
            inline=False,
        )

        selected = self._selected_entry()
        if selected is not None:
            embed.add_field(
                name="Selected",
                value=self._selected_details(selected)[:1024],
                inline=False,
            )

        embed.set_footer(text="Select 1-5, then use actions.")
        return {"embed": embed}

    def _select_index(self, local_index: int) -> None:
        page_start = (self.page - 1) * self.PAGE_SIZE
        absolute_index = page_start + local_index
        if absolute_index < 0 or absolute_index >= len(self.entries):
            return
        self.selected_index = absolute_index

    def _sync_button_state(self) -> None:
        has_entries = len(self.entries) > 0
        self.total_pages = (
            max(1, math.ceil(len(self.entries) / self.PAGE_SIZE)) if has_entries else 1
        )
        self.page = max(1, min(self.page, self.total_pages))

        page_entries = self._page_slice() if has_entries else []
        page_start = (self.page - 1) * self.PAGE_SIZE

        selectors = [
            self.select_1,
            self.select_2,
            self.select_3,
            self.select_4,
            self.select_5,
        ]
        for idx, button in enumerate(selectors):
            has_item = idx < len(page_entries)
            button.disabled = not has_item
            button.label = str(idx + 1)
            if not has_item:
                button.style = discord.ButtonStyle.secondary
                continue
            absolute_index = page_start + idx
            button.style = (
                discord.ButtonStyle.primary
                if absolute_index == self.selected_index
                else discord.ButtonStyle.secondary
            )

        self.prev_page.disabled = (not has_entries) or self.page <= 1
        self.next_page.disabled = (not has_entries) or self.page >= self.total_pages
        self.delete_item.disabled = not has_entries

        selected = self._selected_entry()
        self.item_actions.disabled = (
            selected is None or str(selected.get("entry_type") or "") != "schedule"
        )

    async def _refresh_message(self, interaction: discord.Interaction) -> None:
        self._sync_button_state()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self, **self.payload())
        else:
            await interaction.response.edit_message(view=self, **self.payload())

    @discord.ui.button(label="1", style=discord.ButtonStyle.secondary, row=0)
    async def select_1(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self._select_index(0)
        await self._refresh_message(interaction)

    @discord.ui.button(label="2", style=discord.ButtonStyle.secondary, row=0)
    async def select_2(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self._select_index(1)
        await self._refresh_message(interaction)

    @discord.ui.button(label="3", style=discord.ButtonStyle.secondary, row=0)
    async def select_3(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self._select_index(2)
        await self._refresh_message(interaction)

    @discord.ui.button(label="4", style=discord.ButtonStyle.secondary, row=0)
    async def select_4(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self._select_index(3)
        await self._refresh_message(interaction)

    @discord.ui.button(label="5", style=discord.ButtonStyle.secondary, row=0)
    async def select_5(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self._select_index(4)
        await self._refresh_message(interaction)

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.secondary, row=1)
    async def prev_page(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if self.page <= 1:
            await interaction.response.defer(ephemeral=True)
            return
        self.page -= 1
        self._select_index(0)
        await self._refresh_message(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary, row=1)
    async def next_page(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if self.page >= self.total_pages:
            await interaction.response.defer(ephemeral=True)
            return
        self.page += 1
        self._select_index(0)
        await self._refresh_message(interaction)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary, row=1)
    async def refresh_list(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()
        await self._reload_entries()
        self._sync_button_state()
        if interaction.message is not None:
            await interaction.message.edit(view=self, **self.payload())
        else:
            await interaction.edit_original_response(view=self, **self.payload())

    @discord.ui.button(
        label="Schedule Actions", style=discord.ButtonStyle.primary, row=2
    )
    async def item_actions(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        current = self._selected_entry()
        if current is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="No item selected.",
            )
            return

        if str(current.get("entry_type") or "") != "schedule":
            await interaction.response.send_message(
                ephemeral=True,
                content="Actions are only available for schedules.",
            )
            return

        await interaction.response.send_message(
            ephemeral=True,
            content=f"Actions for schedule `{current.get('job_id')}`.",
            view=ScheduledJobActionView(
                job_id=str(current.get("job_id") or ""),
                channel_id=current.get("channel_id"),
                guild_id=current.get("guild_id"),
            ),
        )

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger, row=2)
    async def delete_item(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        current = self._selected_entry()
        if current is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="No item selected.",
            )
            return

        try:
            if str(current.get("entry_type") or "") == "schedule":
                manager = DailyJobManager()
                deleted = await asyncio.to_thread(
                    manager.delete_job,
                    str(current.get("job_id") or ""),
                    current.get("channel_id"),
                    current.get("guild_id"),
                )
                message = "Schedule deleted." if deleted else "Schedule was not found."
            else:
                deleted = await asyncio.to_thread(
                    deactivate_alert,
                    str(current.get("alert_id") or ""),
                    self.user_id,
                    "stock",
                    self.guild_id,
                )
                message = "Alert deleted." if deleted else "Alert was not found."
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await self._reload_entries()
        self._sync_button_state()
        if interaction.message is not None:
            await interaction.message.edit(view=self, **self.payload())
        else:
            await interaction.edit_original_response(view=self, **self.payload())
        await interaction.followup.send(ephemeral=True, content=message)
