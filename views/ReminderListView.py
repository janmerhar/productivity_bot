import asyncio
import datetime
import math
from typing import List, Optional

import discord

from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from services.channel_visibility import can_view_channel
from services.error_reporting import ValidationError, UserVisibleError, handle_interaction_error
from views.ReminderOutputView import ReminderOutputView
from views.ReminderEditModal import ReminderCreateModal


class ReminderListOptionsModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        parent_view: "ReminderListView",
        source_message: Optional[discord.Message],
        interaction: discord.Interaction,
    ) -> None:
        modal_title = f"View Options - {parent_view.scope_label}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.parent_view = parent_view
        self.source_message = source_message
        default_users = (
            [discord.Object(id=user_id) for user_id in parent_view.ping_filter_user_ids[:25]]
            if parent_view.ping_filter_user_ids
            else []
        )

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
                    default=parent_view.status_filter == "all",
                ),
                discord.RadioGroupOption(
                    label="Active",
                    value="active",
                    default=parent_view.status_filter == "active",
                ),
                discord.RadioGroupOption(
                    label="Paused",
                    value="paused",
                    default=parent_view.status_filter == "paused",
                ),
            ],
        )
        self.search_input = discord.ui.TextInput(
            label="Search",
            placeholder="Name, description, schedule, ID",
            required=False,
            default=parent_view.search_query,
            max_length=100,
        )
        self.ping_user_select = discord.ui.UserSelect(
            custom_id="reminder_list_options_ping_user",
            placeholder="Leave empty for all reminders",
            min_values=0,
            max_values=25,
            required=False,
            default_values=default_users,
        )
        self.destination_select = discord.ui.Select(
            placeholder="Which destination to show",
            min_values=1,
            max_values=1,
            options=parent_view._build_target_select_options(interaction)[:25],
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
        self.add_item(self.search_input)
        self.add_item(
            discord.ui.Label(
                text="Ping Users",
                description="Shows reminders pinging any selected user.",
                component=self.ping_user_select,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Destination",
                component=self.destination_select,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        sort_value = str(self.sort_group.value or "ascending")
        status_value = str(self.status_group.value or "all")
        search_query = self.parent_view.normalize_search_query(self.search_input.value)
        target_value = str(self.destination_select.values[0] or "").strip()
        if sort_value not in {"ascending", "descending"}:
            sort_value = "ascending"
        if status_value not in {"all", "active", "paused"}:
            status_value = "all"

        try:
            selected_users = list(self.ping_user_select.values)
            ping_filter_user_ids: List[int] = []
            ping_filter_label = "All"
            if selected_users:
                ping_filter_user_ids = [
                    int(selected_user.id)
                    for selected_user in selected_users
                    if getattr(selected_user, "id", None) is not None
                ]
                if not ping_filter_user_ids:
                    raise ValidationError(
                        "That user selection could not be resolved.",
                        ephemeral=True,
                    )
                selected_labels = [
                    str(
                        getattr(selected_user, "display_name", "")
                        or getattr(selected_user, "name", "")
                        or f"User {selected_user.id}"
                    ).strip()
                    for selected_user in selected_users
                    if getattr(selected_user, "id", None) is not None
                ]
                if len(selected_labels) == 1:
                    ping_filter_label = selected_labels[0][:100]
                else:
                    ping_filter_label = f"{len(selected_labels)} users"

            self.parent_view.sort = sort_value
            self.parent_view.status_filter = status_value
            self.parent_view.search_query = search_query
            self.parent_view.ping_filter_user_ids = ping_filter_user_ids
            self.parent_view.ping_filter_label = ping_filter_label
            self.parent_view._apply_target_value(interaction, target_value)
            self.parent_view.page = 1
            await self.parent_view._reload_reminders(interaction)
            self.parent_view._build()
        except (ValidationError, UserVisibleError) as exc:
            await handle_interaction_error(
                interaction,
                exc,
            )
            return
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
        target_value: str,
        status_filter: str,
        guild_id: Optional[int],
        channel_id: Optional[int],
        destination_type: Optional[str],
        user_id: Optional[int],
        sort: str = "ascending",
        response_ephemeral: bool = False,
        page: int = 1,
        timeout: float = 300,
    ) -> None:
        super().__init__(timeout=timeout)
        self._all_reminders = list(reminders)
        self.reminders: List[DailyJob] = []
        self.scope_label = scope_label
        self.target_value = target_value
        self.status_filter = (
            status_filter
            if status_filter in {"all", "active", "paused"}
            else "all"
        )
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.destination_type = destination_type
        self.user_id = user_id
        self.search_query = ""
        self.ping_filter_user_ids: List[int] = []
        self.ping_filter_label = "All"
        self.sort = sort if sort in {"ascending", "descending"} else "ascending"
        self.message: Optional[discord.Message] = None
        self.response_ephemeral = bool(response_ephemeral)
        self.page_size = self.PAGE_SIZE
        self.total_pages = 1
        self.page = max(1, page)
        self._apply_filters()
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
    def _default_target_value(guild_id: Optional[int]) -> str:
        return "channel" if guild_id is not None else "private"

    @staticmethod
    def _status_filter_label(status_filter: str) -> str:
        labels = {
            "all": "All",
            "active": "Active",
            "paused": "Paused",
        }
        return labels.get(str(status_filter or "").strip().lower(), "All")

    @staticmethod
    def _paused_filter_for_status(status_filter: str) -> Optional[bool]:
        if status_filter == "active":
            return False
        if status_filter == "paused":
            return True
        return None

    @staticmethod
    def normalize_search_query(value: Optional[str]) -> str:
        return str(value or "").strip()

    @staticmethod
    def format_search_filter_label(value: Optional[str]) -> str:
        text = str(value or "").strip()
        if not text:
            return "All"
        if len(text) <= 24:
            return text
        return f"{text[:21].rstrip()}..."

    @staticmethod
    def _search_text(job: DailyJob) -> str:
        parts = [
            ReminderFunctions.reminder_label(job),
            ReminderListView._detail_text(job) or "",
            ReminderListView._schedule_label(job),
            ReminderListView._destination_label(job),
            str(job.id),
        ]
        return " ".join(str(part or "") for part in parts).lower()

    def _apply_filters(self) -> None:
        filtered_reminders = list(self._all_reminders)
        if self.search_query:
            normalized_query = self.search_query.lower()
            filtered_reminders = [
                reminder
                for reminder in filtered_reminders
                if normalized_query in self._search_text(reminder)
            ]
        if self.ping_filter_user_ids:
            filtered_reminders = [
                reminder
                for reminder in filtered_reminders
                if any(
                    user_id in ReminderFunctions.ping_user_ids(reminder)
                    for user_id in self.ping_filter_user_ids
                )
            ]

        self.reminders = filtered_reminders
        self.total_pages = max(1, math.ceil(len(self.reminders) / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))

    def _build_target_select_options(
        self,
        interaction: discord.Interaction,
    ) -> List[discord.SelectOption]:
        target_value = str(self.target_value or "").strip() or self._default_target_value(
            self.guild_id
        )
        options: List[discord.SelectOption] = []

        def add_option(label: str, value: str) -> None:
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=value,
                    default=value == target_value,
                )
            )

        if interaction.guild is None:
            add_option("Private option", "private")
            return options

        add_option("This Channel", "channel")
        add_option("All Server Reminders", "all_server")
        add_option("Private option", "private")

        guild_channels = list(interaction.guild.text_channels)
        selected_channel_id = self.channel_id if self.destination_type == "channel" else None
        if selected_channel_id is not None:
            selected_channel = interaction.guild.get_channel(selected_channel_id)
            if isinstance(selected_channel, discord.TextChannel):
                guild_channels = [
                    selected_channel,
                    *[
                        channel
                        for channel in guild_channels
                        if channel.id != selected_channel.id
                    ],
                ]

        for channel in guild_channels:
            if len(options) >= 25:
                break
            if not channel.permissions_for(interaction.user).view_channel:
                continue
            add_option(f"#{channel.name}", f"channel:{channel.id}")

        return options[:25]

    def _apply_target_value(
        self,
        interaction: discord.Interaction,
        target_value: str,
    ) -> None:
        resolved_value = str(target_value or "").strip()
        if not resolved_value:
            resolved_value = self._default_target_value(interaction.guild_id)

        if interaction.guild is None:
            if resolved_value != "private":
                raise ValidationError(
                    "Only `Private option` is available in DMs.",
                    ephemeral=True,
                )
            self.target_value = "private"
            self.channel_id = None
            self.destination_type = "private"
            self.scope_label = "Private option"
            return

        if resolved_value == "channel":
            current_channel = interaction.channel
            if not isinstance(current_channel, discord.TextChannel):
                raise ValidationError(
                    "This command must be used in a text channel for `This Channel`.",
                    ephemeral=True,
                )
            self.target_value = "channel"
            self.channel_id = current_channel.id
            self.destination_type = "channel"
            self.scope_label = f"#{current_channel.name}"
            return

        if resolved_value == "all_server":
            self.target_value = "all_server"
            self.channel_id = None
            self.destination_type = "channel"
            self.scope_label = "All Server Reminders"
            return

        if resolved_value == "private":
            self.target_value = "private"
            self.channel_id = None
            self.destination_type = "private"
            self.scope_label = "Private option"
            return

        if resolved_value.startswith("channel:"):
            try:
                channel_id = int(resolved_value.split(":", 1)[1])
            except (TypeError, ValueError):
                raise ValidationError(
                    "Please select a valid channel.",
                    ephemeral=True,
                )
            selected_channel = interaction.guild.get_channel(channel_id)
            if not isinstance(selected_channel, discord.TextChannel):
                raise ValidationError(
                    "That channel is no longer available.",
                    ephemeral=True,
                )
            if not selected_channel.permissions_for(interaction.user).view_channel:
                raise ValidationError(
                    "You can't view that channel.",
                    ephemeral=True,
                )
            self.target_value = f"channel:{channel_id}"
            self.channel_id = channel_id
            self.destination_type = "channel"
            self.scope_label = f"#{selected_channel.name}"
            return

        raise ValidationError(
            "Please choose a valid channel option.",
            ephemeral=True,
        )

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
    def _pause_until_label(job: DailyJob) -> Optional[str]:
        if not ReminderFunctions.is_paused(job):
            return None

        pause_until = ReminderFunctions.pause_until_for_job(job)
        if pause_until is None:
            return None

        return ReminderListView._datetime_label(pause_until.isoformat())

    @staticmethod
    def _detail_text(job: DailyJob) -> Optional[str]:
        values = ReminderFunctions.reminder_edit_values(job)
        detail = str(values.get("description") or "").strip()
        if not detail:
            return None
        return ReminderListView._truncate(detail, 140)

    def _embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"Reminders - {self.scope_label}",
            color=discord.Colour.blurple(),
        )
        status_label = self._status_filter_label(self.status_filter)
        search_label = self.format_search_filter_label(self.search_query)
        ping_label = str(self.ping_filter_label or "All").strip() or "All"

        page_items = self._page_slice()
        if not page_items:
            embed.description = "No reminders found."
            embed.set_footer(
                text=(
                    f"Page {self.page}/{self.total_pages} | Items: {len(self.reminders)} | "
                    f"Sort: {self.sort.title()} | Destination: {self.scope_label} | "
                    f"Status: {status_label} | Search: {search_label} | Ping: {ping_label}"
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
            pause_until_label = self._pause_until_label(job)
            if pause_until_label:
                value_lines.append(f"Paused until: {pause_until_label}")
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
                f"Sort: {self.sort.title()} | Destination: {self.scope_label} | "
                f"Status: {status_label} | Search: {search_label} | Ping: {ping_label}"
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
        return (
            self.status_filter != "all"
            or self.sort != "ascending"
            or bool(self.search_query)
            or bool(self.ping_filter_user_ids)
            or self.target_value != self._default_target_value(self.guild_id)
        )

    @staticmethod
    def _can_view_reminder(
        interaction: discord.Interaction,
        job: DailyJob,
    ) -> bool:
        if ReminderFunctions.is_private_destination(job):
            return ReminderFunctions.destination_user_id(job) == interaction.user.id
        return can_view_channel(interaction, job.channel_id)

    def _filter_visible_reminders(
        self,
        interaction: discord.Interaction,
        reminders: List[DailyJob],
    ) -> List[DailyJob]:
        return [
            reminder
            for reminder in reminders
            if self._can_view_reminder(interaction, reminder)
        ]

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
            await self._reload_reminders(interaction)
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
                interaction=interaction,
            )
        )

    async def _reload_reminders(
        self,
        interaction: Optional[discord.Interaction] = None,
    ) -> None:
        reminders = await asyncio.to_thread(
            ReminderFunctions.list_reminders,
            self.guild_id,
            self._paused_filter_for_status(self.status_filter),
            self.channel_id,
            self.destination_type,
            self.user_id if self.destination_type == "private" else None,
        )
        if interaction is not None:
            reminders = self._filter_visible_reminders(interaction, reminders)
        if self.sort == "descending":
            reminders.reverse()
        self._all_reminders = reminders
        self._apply_filters()

    async def refresh_message(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message] = None,
        jump_to_last_page: bool = False,
    ) -> None:
        await self._reload_reminders(interaction)
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
