import asyncio
import datetime
import math
from typing import Any, Dict, List, Optional, Tuple

import discord

from classes.DailyJobManager import DailyJobManager
from classes.PriceAlertFunctions import fetch_user_active_alerts
from services import stock_list_sessions
from views.ScheduledJobActionView import ScheduledJobActionView
from views.StockAlertActionView import StockAlertActionView


class StockListItemsView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(
        self,
        *,
        user_id: int,
        guild_id: Optional[int],
        channel_id: Optional[int],
        kind: str = "all",
        response_ephemeral: bool = True,
        page: int = 1,
        session_id: Optional[str] = None,
        selected_entry_type: str = "",
        selected_entry_id: str = "",
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.kind = kind if kind in {"all", "schedules", "alerts"} else "all"
        self.response_ephemeral = bool(response_ephemeral)
        self.session_id = str(session_id or "").strip() or None
        self.message: Optional[discord.Message] = None

        self.entries: List[Dict[str, Any]] = []
        self.schedule_count = 0
        self.alert_count = 0

        self.page = max(1, int(page or 1))
        self.total_pages = 1
        self.selected_index = 0
        self._selected_entry_type = str(selected_entry_type or "").strip()
        self._selected_entry_id = str(selected_entry_id or "").strip()

    async def initialize(self) -> None:
        await self._reload_entries()
        await self.ensure_session()

    @classmethod
    async def from_session(
        cls,
        interaction: discord.Interaction,
        session_id: str,
    ) -> Optional["StockListItemsView"]:
        session = await asyncio.to_thread(
            stock_list_sessions.get_session,
            session_id,
        )
        if session is None:
            return None

        view = cls(
            user_id=int(session.get("user_id") or 0),
            guild_id=session.get("guild_id"),
            channel_id=session.get("channel_id"),
            kind=str(session.get("kind") or "all"),
            response_ephemeral=bool(session.get("response_ephemeral", True)),
            page=max(1, int(session.get("page") or 1)),
            session_id=str(session.get("session_id") or session_id).strip(),
            selected_entry_type=str(session.get("selected_entry_type") or ""),
            selected_entry_id=str(session.get("selected_entry_id") or ""),
        )
        view.message = interaction.message
        await view.initialize()
        return view

    async def ensure_session(self) -> str:
        if self.session_id is None:
            self.session_id = await asyncio.to_thread(
                stock_list_sessions.create_session,
                self.session_state(),
            )
        else:
            await self.save_session()
        self._build()
        return self.session_id

    async def save_session(self) -> None:
        if self.session_id is None:
            return
        await asyncio.to_thread(
            stock_list_sessions.save_session,
            self.session_id,
            self.session_state(),
        )

    def session_state(self) -> dict:
        selected = self._selected_entry()
        selected_entry_type = self._selected_entry_type
        selected_entry_id = self._selected_entry_id
        if selected is not None:
            selected_entry_type = str(selected.get("entry_type") or "").strip()
            if selected_entry_type == "schedule":
                selected_entry_id = str(selected.get("job_id") or "").strip()
            else:
                selected_entry_id = str(selected.get("alert_id") or "").strip()

        return {
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "kind": self.kind,
            "response_ephemeral": self.response_ephemeral,
            "page": self.page,
            "selected_entry_type": selected_entry_type,
            "selected_entry_id": selected_entry_id,
        }

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            ephemeral=self.response_ephemeral,
            content="Only the user who opened this list can manage it.",
        )
        return False

    @staticmethod
    def _entry_key(entry: Dict[str, Any]) -> Tuple[str, str]:
        entry_type = str(entry.get("entry_type") or "")
        if entry_type == "schedule":
            return entry_type, str(entry.get("job_id") or "")
        return entry_type, str(entry.get("alert_id") or "")

    def _selected_key(self) -> Optional[Tuple[str, str]]:
        selected = self._selected_entry()
        if selected is not None:
            return self._entry_key(selected)
        if self._selected_entry_type and self._selected_entry_id:
            return self._selected_entry_type, self._selected_entry_id
        return None

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
        previous_key = self._selected_key()
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
                    "paused": bool(item.get("paused")),
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
            self._selected_entry_type = ""
            self._selected_entry_id = ""
            return

        self.total_pages = max(1, math.ceil(len(self.entries) / self.PAGE_SIZE))
        self.page = max(1, min(self.page, self.total_pages))

        selected_index = None
        if previous_key is not None:
            for idx, entry in enumerate(self.entries):
                if self._entry_key(entry) == previous_key:
                    selected_index = idx
                    break

        if selected_index is None:
            page_start = (self.page - 1) * self.PAGE_SIZE
            selected_index = min(page_start, len(self.entries) - 1)

        self.selected_index = selected_index
        self.page = (self.selected_index // self.PAGE_SIZE) + 1
        selected = self._selected_entry()
        if selected is None:
            self._selected_entry_type = ""
            self._selected_entry_id = ""
        else:
            self._selected_entry_type, self._selected_entry_id = self._entry_key(
                selected
            )

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
        self,
        display_index: int,
        entry: Dict[str, Any],
        selected: bool,
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
        self,
        display_index: int,
        entry: Dict[str, Any],
        selected: bool,
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
        status = "paused" if bool(entry.get("paused")) else "active"
        marker = ">" if selected else " "
        return (
            f"{marker}{display_index}. ALR | {symbol} | {trigger} | "
            f"{destination} | {expires} | {status}"
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
        status = "paused" if bool(entry.get("paused")) else "active"
        return (
            f"Type: alert\n"
            f"ID: `{str(entry.get('alert_id') or 'unknown')}`\n"
            f"Symbol: `{str(entry.get('symbol') or 'UNKNOWN')}`\n"
            f"Status: {status}\n"
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
                lines.append(self._schedule_line(display_index, entry, selected))
            else:
                lines.append(self._alert_line(display_index, entry, selected))

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

        embed.set_footer(text="Select 1-5, then use Manage.")
        return {"embed": embed}

    def _select_index(self, local_index: int) -> None:
        page_start = (self.page - 1) * self.PAGE_SIZE
        absolute_index = page_start + local_index
        if absolute_index < 0 or absolute_index >= len(self.entries):
            return
        self.selected_index = absolute_index
        selected = self._selected_entry()
        if selected is None:
            self._selected_entry_type = ""
            self._selected_entry_id = ""
            return
        self._selected_entry_type, self._selected_entry_id = self._entry_key(selected)

    def select_entry_by_reference(self, entry_type: str, entry_id: str) -> bool:
        normalized_entry_type = (
            "schedule" if str(entry_type or "").strip() == "s" else "alert"
        )
        cleaned_entry_id = str(entry_id or "").strip()
        if not cleaned_entry_id:
            return False

        for index, entry in enumerate(self.entries):
            current_type, current_id = self._entry_key(entry)
            if current_type == normalized_entry_type and current_id == cleaned_entry_id:
                self.selected_index = index
                self.page = (index // self.PAGE_SIZE) + 1
                self._selected_entry_type = current_type
                self._selected_entry_id = current_id
                return True
        return False

    def _build(self) -> None:
        self.clear_items()
        if self.session_id is None:
            return

        from views.stock_list_dynamic_items import (
            StockListDeleteButton,
            StockListManageButton,
            StockListNextButton,
            StockListPrevButton,
            StockListRefreshButton,
            StockListSelectButton,
        )

        page_entries = self._page_slice()
        page_start = (self.page - 1) * self.PAGE_SIZE
        for idx in range(self.PAGE_SIZE):
            has_item = idx < len(page_entries)
            entry = page_entries[idx] if has_item else {}
            entry_type, entry_id = self._entry_key(entry) if has_item else ("", "")
            selected = has_item and page_start + idx == self.selected_index
            self.add_item(
                StockListSelectButton(
                    self.session_id,
                    idx,
                    entry_type="s" if entry_type == "schedule" else "a",
                    entry_id=entry_id,
                    disabled=not has_item,
                    selected=selected,
                )
            )

        has_entries = bool(self.entries)
        self.add_item(
            StockListPrevButton(
                self.session_id,
                disabled=(not has_entries) or self.page <= 1,
            )
        )
        self.add_item(
            StockListNextButton(
                self.session_id,
                disabled=(not has_entries) or self.page >= self.total_pages,
            )
        )
        self.add_item(
            StockListRefreshButton(
                self.session_id,
                disabled=not has_entries,
            )
        )
        self.add_item(
            StockListManageButton(
                self.session_id,
                disabled=not has_entries,
            )
        )
        self.add_item(
            StockListDeleteButton(
                self.session_id,
                disabled=not has_entries,
            )
        )

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        self._build()
        await self.save_session()
        if interaction.response.is_done():
            if interaction.message is not None:
                await interaction.message.edit(view=self, **self.payload())
                return
            await interaction.edit_original_response(view=self, **self.payload())
            return
        await interaction.response.edit_message(view=self, **self.payload())

    async def send_selected_item_actions(
        self,
        interaction: discord.Interaction,
    ) -> None:
        current = self._selected_entry()
        if current is None:
            await interaction.response.send_message(
                ephemeral=self.response_ephemeral,
                content="No item selected.",
            )
            return

        entry_type = str(current.get("entry_type") or "")
        if entry_type == "schedule":
            await interaction.response.send_message(
                ephemeral=self.response_ephemeral,
                content=f"Actions for schedule `{current.get('job_id')}`.",
                view=ScheduledJobActionView(
                    job_id=str(current.get("job_id") or ""),
                    channel_id=current.get("channel_id"),
                    guild_id=current.get("guild_id"),
                    response_ephemeral=self.response_ephemeral,
                ),
            )
            return

        if entry_type == "alert":
            alert_view = StockAlertActionView(
                alert_id=str(current.get("alert_id") or ""),
                user_id=self.user_id,
                guild_id=self.guild_id,
                response_ephemeral=self.response_ephemeral,
            )
            await alert_view.initialize()
            await interaction.response.send_message(
                ephemeral=self.response_ephemeral,
                view=alert_view,
                **alert_view.payload(),
            )
            return

        await interaction.response.send_message(
            ephemeral=self.response_ephemeral,
            content="No actions available for this item.",
        )
