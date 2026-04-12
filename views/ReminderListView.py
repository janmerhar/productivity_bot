import asyncio
import datetime
import math
from typing import List, Optional

import discord

from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from services.error_reporting import UserVisibleError, handle_interaction_error
from views.ReminderOutputView import ReminderOutputView
from views.ReminderEditModal import ReminderCreateModal


class ReminderListOptionsModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        parent_view: "ReminderListView",
        source_message: Optional[discord.Message],
    ) -> None:
        modal_title = f"View Options • {parent_view.scope_label}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.parent_view = parent_view
        self.source_message = source_message

        self.sort_group = discord.ui.RadioGroup(
            custom_id="reminder_list_options_sort",
            options=[
                discord.RadioGroupOption(
                    label="Ascending",
                    value="ascending",
                    default=parent_view.sort == "ascending",
                ),
                discord.RadioGroupOption(
                    label="Descending",
                    value="descending",
                    default=parent_view.sort == "descending",
                ),
            ],
        )
        self.status_group = discord.ui.RadioGroup(
            custom_id="reminder_list_options_status",
            options=[
                discord.RadioGroupOption(
                    label="All",
                    value="all",
                    default=parent_view.status_label == "All",
                ),
                discord.RadioGroupOption(
                    label="Active",
                    value="active",
                    default=parent_view.status_label == "Active",
                ),
                discord.RadioGroupOption(
                    label="Paused",
                    value="paused",
                    default=parent_view.status_label == "Paused",
                ),
            ],
        )

        self.add_item(
            discord.ui.Label(
                text="Sort",
                component=self.sort_group,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Status",
                component=self.status_group,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        sort_value = str(self.sort_group.value or "ascending")
        status_value = str(self.status_group.value or "all")
        if sort_value not in {"ascending", "descending"}:
            sort_value = "ascending"
        if status_value == "active":
            paused_filter = False
            status_label = "Active"
        elif status_value == "paused":
            paused_filter = True
            status_label = "Paused"
        else:
            paused_filter = None
            status_label = "All"

        self.parent_view.sort = sort_value
        self.parent_view.paused_filter = paused_filter
        self.parent_view.status_label = status_label
        self.parent_view.page = 1

        try:
            await self.parent_view._reload_reminders()
            self.parent_view._build()
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while updating the list options.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        target_message = self.source_message or self.parent_view.message
        if target_message is None:
            await interaction.followup.send(
                ephemeral=True,
                view=self.parent_view,
                **self.parent_view.payload(),
            )
            return

        try:
            await target_message.edit(
                view=self.parent_view,
                **self.parent_view.payload(),
            )
            self.parent_view.message = target_message
        except discord.NotFound:
            await self.parent_view._notify_missing_message(interaction)
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Options updated, but refreshing the list failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )


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
        destination_type: Optional[str],
        paused_filter: Optional[bool],
        user_id: Optional[int],
        sort: str = "ascending",
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
        self.destination_type = destination_type
        self.paused_filter = paused_filter
        self.user_id = user_id
        self.sort = sort if sort in {"ascending", "descending"} else "ascending"
        self.message: Optional[discord.Message] = None
        self.response_ephemeral = bool(response_ephemeral)
        self.page_size = self.PAGE_SIZE
        self.total_pages = max(1, math.ceil(len(self.reminders) / self.page_size))
        self.page = max(1, min(page, self.total_pages))
        self._build()

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
    def _number_emoji(value: int) -> str:
        digits = {
            "0": "0️⃣",
            "1": "1️⃣",
            "2": "2️⃣",
            "3": "3️⃣",
            "4": "4️⃣",
            "5": "5️⃣",
            "6": "6️⃣",
            "7": "7️⃣",
            "8": "8️⃣",
            "9": "9️⃣",
        }
        return "".join(digits.get(ch, ch) for ch in str(value))

    @staticmethod
    def _truncate(text: str, limit: int = 80) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3].rstrip()}..."

    @staticmethod
    def _destination_label(job: DailyJob) -> str:
        return ReminderFunctions.destination_label(job)

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

    @staticmethod
    def _detail_text(job: DailyJob) -> Optional[str]:
        values = ReminderFunctions.reminder_edit_values(job)
        detail = str(values.get("description") or "").strip()
        if not detail:
            return None
        return ReminderListView._truncate(detail, 140)

    def _embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"Reminders • {self.scope_label}",
            color=discord.Colour.blurple(),
        )

        page_items = self._page_slice()
        if not page_items:
            embed.description = "No reminders found."
            embed.set_footer(
                text=(
                    f"Page {self.page}/{self.total_pages} | Items: {len(self.reminders)} | "
                    f"Sort: {self.sort.title()} | Scope: {self.scope_label} | "
                    f"Status: {self.status_label}"
                )
            )
            return embed

        for display_index, job in enumerate(page_items, start=1):
            label = self._truncate(ReminderFunctions.reminder_label(job), 90)
            status = "Paused" if ReminderFunctions.is_paused(job) else "Active"
            value_lines = [
                f"Schedule: {self._schedule_label(job)}",
                f"Destination: {self._destination_label(job)} | ID: `{str(job.id)[:8]}`",
            ]
            expires_label = self._expires_label(job)
            if expires_label:
                value_lines.append(f"Expires: {expires_label}")
            detail_text = self._detail_text(job)
            if detail_text and detail_text.lower() != label.lower():
                value_lines.insert(0, detail_text)
            embed.add_field(
                name=f"{self._number_emoji(display_index)} {label} [{status}]",
                value="\n".join(value_lines),
                inline=False,
            )

        embed.set_footer(
            text=(
                f"Page {self.page}/{self.total_pages} | Items: {len(self.reminders)} | "
                f"Sort: {self.sort.title()} | Scope: {self.scope_label} | "
                f"Status: {self.status_label}"
            )
        )
        return embed

    def payload(self) -> dict:
        return {"embed": self._embed()}

    def _page_item(self, slot_index: int) -> Optional[DailyJob]:
        page_items = self._page_slice()
        if 0 <= slot_index < len(page_items):
            return page_items[slot_index]
        return None

    def _has_active_list_options(self) -> bool:
        return self.paused_filter is not None or self.sort != "ascending"

    async def _notify_missing_message(self, interaction: discord.Interaction) -> None:
        message = (
            "That reminder list message is no longer available. "
            "Run `/reminder list` again."
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(ephemeral=True, content=message)
            else:
                await interaction.response.send_message(ephemeral=True, content=message)
        except Exception:
            return

    async def _open_reminder_details(
        self,
        interaction: discord.Interaction,
        job: Optional[DailyJob],
    ) -> None:
        if job is None:
            await interaction.response.defer(ephemeral=True)
            return

        current_job = await asyncio.to_thread(
            ReminderFunctions.get_reminder,
            str(job.id),
            self.guild_id,
        )
        if current_job is None:
            await self._reload_reminders()
            self._build()
            await interaction.response.edit_message(view=self, **self.payload())
            return

        output_view = ReminderOutputView(
            job=current_job,
            guild=interaction.guild,
            result_message=f"Showing reminder `{str(current_job.id)}`.",
            ok=True,
            user_id=interaction.user.id,
            response_ephemeral=True,
        )
        await interaction.response.send_message(
            ephemeral=True,
            **output_view.response_payload(),
        )

    async def open_create_modal(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message],
    ) -> None:
        default_channel_id = self.channel_id or interaction.channel_id
        await interaction.response.send_modal(
            ReminderCreateModal(
                parent_view=self,
                default_channel_id=default_channel_id,
                default_destination_type=self.destination_type or "channel",
                guild=interaction.guild,
                source_message=source_message,
                response_ephemeral=self.response_ephemeral,
            )
        )

    async def open_options_modal(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message],
    ) -> None:
        await interaction.response.send_modal(
            ReminderListOptionsModal(
                parent_view=self,
                source_message=source_message,
            )
        )

    async def _reload_reminders(self) -> None:
        reminders = await asyncio.to_thread(
            ReminderFunctions.list_reminders,
            self.guild_id,
            self.paused_filter,
            self.channel_id,
            self.destination_type,
            self.user_id if self.destination_type == "private" else None,
        )
        if self.sort == "descending":
            reminders.reverse()
        self.reminders = reminders
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
        self._build()

        target_message = source_message or interaction.message
        if target_message is None:
            return

        try:
            await target_message.edit(view=self, **self.payload())
            self.message = target_message
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(
                "Reminder created, but the original list message is no longer available.",
                ephemeral=self.response_ephemeral,
            )

    def _build(self) -> None:
        self.clear_items()

        for slot_index in range(self.page_size):
            display_index = slot_index + 1
            job = self._page_item(slot_index)
            job_id = str(job.id) if job is not None else ""

            info_button = discord.ui.Button(
                label=str(display_index),
                style=discord.ButtonStyle.secondary,
                custom_id=f"reminder_item_info:{job_id or display_index}",
                row=0,
                disabled=job is None,
            )

            async def _info_callback(
                interaction: discord.Interaction,
                job_data: Optional[DailyJob] = job,
            ) -> None:
                await self._open_reminder_details(interaction, job_data)

            info_button.callback = _info_callback
            self.add_item(info_button)

        prev_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="◀️",
            disabled=self.page <= 1,
            row=1,
        )
        add_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            emoji="➕",
            row=1,
        )
        next_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="▶️",
            disabled=self.page >= self.total_pages,
            row=1,
        )
        options_button = discord.ui.Button(
            style=(
                discord.ButtonStyle.success
                if self._has_active_list_options()
                else discord.ButtonStyle.secondary
            ),
            emoji="🔎",
            row=1,
        )

        async def _prev_callback(interaction: discord.Interaction) -> None:
            if self.page <= 1:
                await interaction.response.defer(ephemeral=True)
                return
            self.page -= 1
            self._build()
            await interaction.response.edit_message(view=self, **self.payload())

        async def _next_callback(interaction: discord.Interaction) -> None:
            if self.page >= self.total_pages:
                await interaction.response.defer(ephemeral=True)
                return
            self.page += 1
            self._build()
            await interaction.response.edit_message(view=self, **self.payload())

        async def _add_callback(interaction: discord.Interaction) -> None:
            await self.open_create_modal(
                interaction,
                source_message=interaction.message,
            )

        async def _options_callback(interaction: discord.Interaction) -> None:
            await self.open_options_modal(
                interaction,
                source_message=interaction.message,
            )

        prev_button.callback = _prev_callback
        add_button.callback = _add_callback
        next_button.callback = _next_callback
        options_button.callback = _options_callback

        self.add_item(prev_button)
        self.add_item(next_button)
        self.add_item(add_button)
        self.add_item(options_button)
