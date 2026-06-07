import asyncio
import math
from typing import Dict, List, Optional

import discord

from classes.HabitFunctions import HabitFunctions
from embeds.HabitEmbeds import HabitEmbeds
from services import habit_list_sessions
from services.discord_helpers import normalize_habit_list_scope
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)
from views.HabitActionView import HabitActionView


class HabitListOptionsModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        parent_view: "HabitListView",
        source_message: Optional[discord.Message],
        interaction: discord.Interaction,
    ) -> None:
        modal_title = f"View Options - {parent_view.scope_label or 'Habits'}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.parent_view = parent_view
        self.source_message = source_message

        self.sort_group = discord.ui.RadioGroup(
            custom_id="habit_list_options_sort",
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
            custom_id="habit_list_options_status",
            options=[
                discord.RadioGroupOption(
                    label="All",
                    value="all",
                    default=parent_view.mode == "all",
                ),
                discord.RadioGroupOption(
                    label="Incomplete",
                    value="incomplete",
                    default=parent_view.mode == "incomplete",
                ),
                discord.RadioGroupOption(
                    label="Skipped",
                    value="skipped",
                    default=parent_view.mode == "skipped",
                ),
            ],
        )
        self.scope_select = discord.ui.Select(
            placeholder="Which habits to show",
            min_values=1,
            max_values=1,
            options=parent_view._build_scope_select_options(interaction)[:25],
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
        self.add_item(
            discord.ui.Label(
                text="Scope",
                component=self.scope_select,
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        sort_value = str(self.sort_group.value or "ascending")
        status_value = str(self.status_group.value or "all")
        scope_value = (
            str(self.scope_select.values[0] or "").strip()
            if self.scope_select.values
            else ""
        )

        if sort_value not in {"ascending", "descending"}:
            sort_value = "ascending"
        if status_value not in {"all", "incomplete", "skipped"}:
            status_value = "all"

        try:
            self.parent_view.sort = sort_value
            self.parent_view.mode = status_value
            self.parent_view._apply_scope_value(interaction, scope_value)
            self.parent_view.page = 1
            refreshed = await self.parent_view.refresh_message(
                interaction,
                source_message=self.source_message,
            )
            if not refreshed:
                raise UserVisibleError(
                    "Options updated, but refreshing the habit list failed.",
                    ephemeral=True,
                )
        except (ValidationError, UserVisibleError) as exc:
            await handle_interaction_error(interaction, exc)
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while updating the habit list.",
                    ephemeral=True,
                    cause=exc,
                ),
            )


class HabitListView(discord.ui.View):
    PAGE_SIZE = 5

    def __init__(
        self,
        *,
        habits: List[Dict],
        scope_label: str,
        scope_value: str,
        mode: str,
        guild_id: Optional[int],
        channel_id: Optional[int],
        user_id: Optional[int],
        response_ephemeral: bool = False,
        page: int = 1,
        sort: str = "ascending",
        session_id: Optional[str] = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self._all_habits = list(habits)
        self.habits: List[Dict] = []
        self.scope_label = str(scope_label or "").strip()
        normalized_scope = str(scope_value or "").strip().lower()
        if normalized_scope == "personal":
            self.scope_value = "personal"
        elif normalized_scope in {"guild", "server", "all_server"}:
            self.scope_value = "guild"
        else:
            self.scope_value = "channel"
        normalized_mode = str(mode or "").strip().lower()
        if normalized_mode == "incomplete":
            self.mode = "incomplete"
        elif normalized_mode == "skipped":
            self.mode = "skipped"
        else:
            self.mode = "all"
        self.sort = "descending" if str(sort or "").strip() == "descending" else "ascending"
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.user_id = user_id
        self.response_ephemeral = bool(response_ephemeral)
        self.page_size = self.PAGE_SIZE
        self.total_pages = 1
        self.page = max(1, int(page or 1))
        self.session_id = str(session_id or "").strip() or None
        self.message: Optional[discord.Message] = None
        self._apply_sort()
        if self.session_id is not None:
            self._build()

    @classmethod
    async def from_session(
        cls,
        interaction: discord.Interaction,
        session_id: str,
    ) -> Optional["HabitListView"]:
        session = await asyncio.to_thread(
            habit_list_sessions.get_session,
            session_id,
        )
        if session is None:
            return None

        habits = await asyncio.to_thread(
            HabitFunctions.list_habits,
            session.get("guild_id"),
            session.get("user_id"),
            session.get("channel_id"),
            str(session.get("mode") or "all"),
            str(session.get("scope_value") or "channel"),
        )
        view = cls(
            habits=habits,
            scope_label=str(session.get("scope_label") or "").strip(),
            scope_value=str(session.get("scope_value") or "channel").strip(),
            mode=str(session.get("mode") or "all").strip(),
            guild_id=session.get("guild_id"),
            channel_id=session.get("channel_id"),
            user_id=session.get("user_id"),
            response_ephemeral=bool(session.get("response_ephemeral", False)),
            page=max(1, int(session.get("page") or 1)),
            sort=str(session.get("sort") or "ascending").strip(),
            session_id=str(session.get("session_id") or session_id).strip(),
        )
        view.message = interaction.message
        await view.ensure_session()
        return view

    def session_state(self) -> dict:
        return {
            "scope_label": self.scope_label,
            "scope_value": self.scope_value,
            "mode": self.mode,
            "sort": self.sort,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "user_id": self.user_id,
            "page": self.page,
            "response_ephemeral": self.response_ephemeral,
        }

    async def ensure_session(self) -> str:
        if self.session_id is None:
            self.session_id = await asyncio.to_thread(
                habit_list_sessions.create_session,
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
            habit_list_sessions.save_session,
            self.session_id,
            self.session_state(),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id is None or interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            "Only the user who opened this habit list can manage it.",
            ephemeral=self.response_ephemeral,
        )
        return False

    def _apply_sort(self) -> None:
        self.habits = list(self._all_habits)
        if self.sort == "descending":
            self.habits.reverse()
        self.total_pages = max(1, math.ceil(len(self.habits) / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))

    def _page_slice(self) -> List[Dict]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.habits[start:end]

    def _page_item(self, slot_index: int) -> Optional[Dict]:
        page_items = self._page_slice()
        if 0 <= slot_index < len(page_items):
            return page_items[slot_index]
        return None

    @staticmethod
    def _number_emoji(value: int) -> str:
        digits = {
            "0": "0️⃣", "1": "1️⃣", "2": "2️⃣", "3": "3️⃣", "4": "4️⃣",
            "5": "5️⃣", "6": "6️⃣", "7": "7️⃣", "8": "8️⃣", "9": "9️⃣",
        }
        return "".join(digits.get(ch, ch) for ch in str(value))

    def _active_filters_footer(self) -> str:
        sort_arrow = "↑" if self.sort == "ascending" else "↓"
        parts = [f"{sort_arrow} {self.sort.title()}"]
        if self.mode and self.mode.lower() != "all":
            parts.append(f"Status: {self._mode_label()}")
        return "  ·  ".join(parts)

    @staticmethod
    def _truncate(text: str, limit: int = 120) -> str:
        cleaned = str(text or "").strip()
        if len(cleaned) <= limit:
            return cleaned
        return f"{cleaned[: limit - 3].rstrip()}..."

    def _mode_label(self) -> str:
        if self.mode == "incomplete":
            return "Incomplete"
        if self.mode == "skipped":
            return "Skipped"
        return "All"

    def _default_scope_value(self) -> str:
        if self.guild_id is None:
            return "personal"
        return "guild"

    def _scope_filter_label(self) -> str:
        if self.scope_value == "personal":
            return "Personal"
        if self.scope_value == "guild":
            return "All Server Habits"
        return self.scope_label or "This Channel"

    def _has_active_list_options(self) -> bool:
        return (
            self.sort != "ascending"
            or self.mode != "all"
            or self.scope_value != self._default_scope_value()
        )

    def _title(self) -> str:
        if self.scope_label:
            return f"Habits - {self.scope_label}"
        return "Habits"

    def _empty_description(self) -> str:
        if self.mode == "incomplete":
            return "No incomplete habits for today."
        if self.mode == "skipped":
            return "No skipped habits for today."
        return "No habits found."

    def _embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=self._title(),
            color=discord.Colour.blurple(),
        )

        filters_text = self._active_filters_footer()
        footer_text = (
            f"Page {self.page} of {self.total_pages}  ·  "
            f"{len(self.habits)} habits  ·  {filters_text}"
        )

        page_habits = self._page_slice()
        if not page_habits:
            embed.description = self._empty_description()
            embed.set_footer(text=footer_text)
            return embed

        status_emojis = {
            "complete": "✅",
            "skip": "⏭️",
            "incomplete": "❌",
        }

        for display_index, habit in enumerate(page_habits, start=1):
            name = self._truncate(str(habit.get("name") or "Habit"), 100) or "Habit"
            description = self._truncate(str(habit.get("description") or ""), 180)
            status = HabitFunctions.today_status(habit)
            progress = HabitFunctions.recent_progress(habit, days=5)

            status_emoji = status_emojis.get(str(status or "").lower(), "⬜")
            number_emoji = self._number_emoji(display_index)

            value_lines = []
            if description and description.lower() != name.lower():
                value_lines.append(description)
            if progress:
                emojis = [HabitEmbeds._PROGRESS_EMOJI.get(mode, "❌") for mode in progress]
                value_lines.append(" ".join(emojis))
            if not value_lines:
                value_lines.append("No details")

            embed.add_field(
                name=f"{number_emoji} {status_emoji} {name}",
                value="\n".join(value_lines),
                inline=False,
            )

        embed.set_footer(text=footer_text)
        return embed

    def payload(self) -> dict:
        return {"embed": self._embed()}

    def _build_scope_select_options(
        self,
        interaction: discord.Interaction,
    ) -> List[discord.SelectOption]:
        if interaction.guild is None:
            return [
                discord.SelectOption(
                    label="Personal",
                    value="personal",
                    default=self.scope_value == "personal",
                )
            ]

        current_value = "guild"
        if self.scope_value == "channel" and self.channel_id is not None:
            current_value = f"channel:{self.channel_id}"
        elif self.scope_value == "personal":
            current_value = "personal"

        options: List[discord.SelectOption] = [
            discord.SelectOption(
                label="All Server Habits",
                value="guild",
                default=current_value == "guild",
            )
        ]

        if interaction.channel_id is not None:
            options.append(
                discord.SelectOption(
                    label="This Channel",
                    value="current",
                    default=(
                        self.scope_value == "channel"
                        and self.channel_id == interaction.channel_id
                    ),
                )
            )

        selected_channel = (
            interaction.guild.get_channel(self.channel_id)
            if self.scope_value == "channel" and self.channel_id is not None
            else None
        )
        guild_channels = list(interaction.guild.text_channels)
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
            if len(options) >= 24:
                break
            if interaction.channel_id is not None and channel.id == interaction.channel_id:
                continue
            if not channel.permissions_for(interaction.user).view_channel:
                continue
            options.append(
                discord.SelectOption(
                    label=f"#{channel.name}"[:100],
                    value=f"channel:{channel.id}",
                    default=current_value == f"channel:{channel.id}",
                )
            )

        if len(options) < 25:
            options.append(
                discord.SelectOption(
                    label="Personal",
                    value="personal",
                    default=current_value == "personal",
                )
            )

        return options[:25]

    def _apply_scope_value(
        self,
        interaction: discord.Interaction,
        target_value: str,
    ) -> None:
        try:
            scope_value, target_channel_id, scope_label = normalize_habit_list_scope(
                interaction,
                target_value,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=True, cause=exc) from exc
        self.scope_value = scope_value
        self.channel_id = target_channel_id
        if scope_value == "channel" and interaction.guild is not None and target_channel_id is not None:
            selected_channel = interaction.guild.get_channel(target_channel_id)
            if isinstance(selected_channel, discord.TextChannel):
                scope_label = f"#{selected_channel.name}"
            else:
                scope_label = f"Channel {target_channel_id}"
        self.scope_label = scope_label

    async def _reload_habits(self) -> None:
        self._all_habits = await asyncio.to_thread(
            HabitFunctions.list_habits,
            self.guild_id,
            self.user_id,
            self.channel_id,
            self.mode,
            self.scope_value,
        )
        self._apply_sort()

    async def _notify_missing_message(self, interaction: discord.Interaction) -> None:
        message = "That habit list is no longer available. Run `/habit list` again."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(ephemeral=True, content=message)
            else:
                await interaction.response.send_message(ephemeral=True, content=message)
        except Exception:
            return

    async def refresh_message(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message] = None,
        jump_to_last_page: bool = False,
        result_message: Optional[str] = None,
    ) -> bool:
        del result_message
        await self._reload_habits()
        if jump_to_last_page and self.habits:
            self.page = self.total_pages if self.sort == "ascending" else 1
        self._build()
        await self.save_session()

        target_message = source_message or interaction.message or self.message
        if target_message is None:
            posted_message = await interaction.followup.send(
                ephemeral=self.response_ephemeral,
                view=self,
                wait=True,
                **self.payload(),
            )
            self.message = posted_message
            return True

        try:
            await target_message.edit(view=self, **self.payload())
            self.message = target_message
            return True
        except discord.NotFound:
            pass
        except (discord.Forbidden, discord.HTTPException):
            pass

        target_message_id = getattr(target_message, "id", None)
        if target_message_id is not None:
            try:
                await interaction.followup.edit_message(
                    target_message_id,
                    view=self,
                    **self.payload(),
                )
                self.message = target_message
                return True
            except discord.NotFound:
                await self._notify_missing_message(interaction)
                return False
            except (discord.Forbidden, discord.HTTPException):
                return False

        await self._notify_missing_message(interaction)
        return False

    async def _safe_refresh_message(self, interaction: discord.Interaction) -> bool:
        self._build()
        await self.save_session()
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self, **self.payload())
            else:
                await interaction.response.edit_message(view=self, **self.payload())
            self.message = interaction.message
            return True
        except discord.NotFound:
            await self._notify_missing_message(interaction)
            return False

    async def open_habit_details(
        self,
        interaction: discord.Interaction,
        habit: Optional[Dict],
    ) -> None:
        habit_id = str((habit or {}).get("_id") or "").strip()
        if not habit_id:
            await interaction.response.defer(ephemeral=self.response_ephemeral)
            return

        current_habit = await asyncio.to_thread(
            HabitFunctions.fetch_habit,
            habit_id,
            self.guild_id,
            self.user_id,
        )
        if current_habit is None:
            await self._reload_habits()
            await self._safe_refresh_message(interaction)
            return

        habit_cog = interaction.client.get_cog("HabitCog")
        payload = HabitEmbeds.habit_item_embed(
            current_habit,
            HabitFunctions.today_status(current_habit),
            HabitFunctions.recent_progress(current_habit, days=5),
        )

        if habit_cog is not None and hasattr(habit_cog, "_build_created_habit_view"):
            payload["view"] = habit_cog._build_created_habit_view(
                current_habit,
                ephemeral=self.response_ephemeral,
            )
        else:
            payload["view"] = HabitActionView(
                habit_id,
                str(current_habit.get("name") or "Habit"),
                interaction.user.id,
                today_status=HabitFunctions.today_status(current_habit),
            )

        await interaction.response.defer(ephemeral=self.response_ephemeral)
        posted_message = await interaction.followup.send(
            ephemeral=self.response_ephemeral,
            wait=True,
            **payload,
        )
        payload["view"].message = posted_message

    async def open_create_modal(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message],
    ) -> None:
        from views.HabitCreateModal import HabitCreateModal

        habit_cog = interaction.client.get_cog("HabitCog")
        if habit_cog is None:
            await interaction.response.send_message(
                "The habit cog is not available right now.",
                ephemeral=True,
            )
            return

        default_scope = self.scope_value
        default_channel_id = self.channel_id
        if default_scope == "guild":
            default_scope = "channel" if interaction.guild_id is not None else "personal"
            default_channel_id = interaction.channel_id if default_scope == "channel" else None

        await interaction.response.send_modal(
            HabitCreateModal(
                habit_cog,
                user_id=interaction.user.id,
                scope_value=default_scope,
                target_channel_id=default_channel_id,
                response_ephemeral=self.response_ephemeral,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                include_scope_select=True,
                source_view=self,
                source_message=source_message,
            )
        )

    async def open_options_modal(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message],
    ) -> None:
        try:
            await interaction.response.send_modal(
                HabitListOptionsModal(
                    parent_view=self,
                    source_message=source_message,
                    interaction=interaction,
                )
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Couldn't open the habit list options.",
                    ephemeral=True,
                    cause=exc,
                ),
            )

    def _build(self) -> None:
        self.clear_items()
        if self.session_id is None:
            return

        from views.habit_list_dynamic_items import (
            HabitListAddButton,
            HabitListNextButton,
            HabitListOptionsButton,
            HabitListPrevButton,
            HabitListShowButton,
        )

        for slot_index in range(self.page_size):
            habit = self._page_item(slot_index)
            self.add_item(
                HabitListShowButton(
                    self.session_id,
                    slot_index,
                    habit_id=str((habit or {}).get("_id") or "") if habit else "",
                    disabled=habit is None,
                )
            )

        self.add_item(
            HabitListPrevButton(
                self.session_id,
                disabled=self.page <= 1,
            )
        )
        self.add_item(
            HabitListNextButton(
                self.session_id,
                disabled=self.page >= self.total_pages,
            )
        )
        self.add_item(HabitListAddButton(self.session_id))
        self.add_item(
            HabitListOptionsButton(
                self.session_id,
                active=self._has_active_list_options(),
            )
        )
