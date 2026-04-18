import asyncio
import math
from typing import Any, Dict, List, Optional

import discord

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds
from services import todo_list_directory_sessions
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)
from views.TodoListDescriptionView import TodoListDescriptionView


class TodoListDirectoryCreateModal(discord.ui.Modal):
    def __init__(self, parent_view: "TodoListDirectoryView") -> None:
        super().__init__(title="Create New List")
        self.parent_view = parent_view
        self.name_input = discord.ui.TextInput(
            label="List name",
            placeholder="Work, Errands, Reading",
            required=True,
            max_length=TodoFunctions._MAX_LIST_NAME_LEN,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if (
            self.parent_view.user_id is not None
            and interaction.user.id != self.parent_view.user_id
        ):
            await interaction.response.send_message(
                "Only the user who opened this list directory can use these controls.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.create_todo_list,
                self.parent_view.guild_id,
                interaction.user.id,
                None,
                str(self.name_input.value or ""),
                self.parent_view.directory_scope_value,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(str(exc), ephemeral=True, cause=exc),
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while creating that list.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        try:
            await self.parent_view.refresh_entries()
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "The list was created, but refreshing the directory failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        self.parent_view.focus_list(todo_list.get("_id"))
        await self.parent_view.refresh_message(interaction)

        result_view = TodoListDescriptionView(
            title="Todo List Created",
            description=(
                f"List: `{todo_list.get('name') or 'List'}`\n"
                f"Items: `0`"
            ),
            color=discord.Colour.green(),
            todo_list=todo_list,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(
            ephemeral=True,
            **result_view.response_payload(),
        )


class TodoListDirectoryView(discord.ui.View):
    def __init__(
        self,
        *,
        server_lists: List[Dict[str, Any]],
        personal_lists: List[Dict[str, Any]],
        current_scope: str,
        guild_id: Optional[int],
        channel_id: Optional[int],
        channel_name: Optional[str],
        user_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 5,
        sort_direction: str = "ascending",
        session_id: Optional[str] = None,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.current_scope = current_scope if current_scope == "personal" else "server"
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.channel_name = channel_name
        self.user_id = user_id
        self.message: Optional[discord.Message] = None
        self.sort_direction = (
            "descending" if sort_direction == "descending" else "ascending"
        )
        self.session_id = str(session_id or "").strip() or None
        self.entries = [
            *[self._normalize_entry("Server", entry) for entry in server_lists],
            *[self._normalize_entry("Personal", entry) for entry in personal_lists],
        ]
        self.page_size = max(1, min(page_size, 5))
        self._sort_entries()
        self.total_pages = max(1, math.ceil(len(self.entries) / self.page_size))
        self.page = max(1, min(page, self.total_pages))
        if self.session_id is not None:
            self._build()

    @classmethod
    async def from_session(
        cls,
        interaction: discord.Interaction,
        session_id: str,
    ) -> Optional["TodoListDirectoryView"]:
        session = await asyncio.to_thread(
            todo_list_directory_sessions.get_session,
            session_id,
        )
        if session is None:
            return None

        view = cls(
            server_lists=[],
            personal_lists=[],
            current_scope=str(session.get("current_scope") or "server"),
            guild_id=session.get("guild_id"),
            channel_id=session.get("channel_id"),
            channel_name=session.get("channel_name"),
            user_id=session.get("user_id"),
            page=max(1, int(session.get("page") or 1)),
            page_size=max(1, int(session.get("page_size") or 5)),
            sort_direction=str(session.get("sort_direction") or "ascending"),
            session_id=str(session.get("session_id") or session_id).strip(),
        )
        view.message = interaction.message
        await view.refresh_entries()
        await view.ensure_session()
        return view

    def session_state(self) -> dict:
        return {
            "current_scope": self.current_scope,
            "guild_id": self.guild_id,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "user_id": self.user_id,
            "page": self.page,
            "page_size": self.page_size,
            "sort_direction": self.sort_direction,
        }

    async def ensure_session(self) -> str:
        if self.session_id is None:
            self.session_id = await asyncio.to_thread(
                todo_list_directory_sessions.create_session,
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
            todo_list_directory_sessions.save_session,
            self.session_id,
            self.session_state(),
        )

    @staticmethod
    def _normalize_entry(scope: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        item_count = int(entry.get("item_count") or 0)
        label = str(entry.get("label") or "").strip()
        name = str(entry.get("name") or "Unnamed").strip() or "Unnamed"
        return {
            "_id": entry.get("_id"),
            "scope": scope,
            "label": label,
            "name": name,
            "item_count": item_count,
        }

    @property
    def directory_scope_value(self) -> str:
        return "personal" if self.current_scope == "personal" else "channel"

    @property
    def total_lists(self) -> int:
        return len(self.entries)

    @property
    def total_items(self) -> int:
        return sum(int(entry.get("item_count") or 0) for entry in self.entries)

    def _page_slice(self) -> List[Dict[str, Any]]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.entries[start:end]

    def _sort_entries(self) -> None:
        reverse = self.sort_direction == "descending"
        self.entries.sort(
            key=lambda entry: (
                str(entry.get("name") or "").lower(),
                str(entry.get("label") or "").lower(),
            ),
            reverse=reverse,
        )

    def _page_entry(self, slot_index: int) -> Optional[Dict[str, Any]]:
        page_entries = self._page_slice()
        if 0 <= slot_index < len(page_entries):
            return page_entries[slot_index]
        return None

    def payload(self) -> dict:
        return TodoEmbeds.list_directory_page_embed(
            self._page_slice(),
            page=self.page,
            total_pages=self.total_pages,
            total_lists=self.total_lists,
            total_items=self.total_items,
            sort_direction=self.sort_direction,
        )

    async def refresh_entries(self) -> None:
        server_lists: List[Dict[str, Any]] = []
        personal_lists: List[Dict[str, Any]] = []

        if self.current_scope == "server" and self.guild_id is not None:
            inbox_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_server_global_list,
                self.guild_id,
                self.user_id,
            )
            server_lists.append(
                {
                    "_id": inbox_list.get("_id"),
                    "label": "Built-in",
                    "name": TodoFunctions.display_list_name(inbox_list, "Inbox"),
                }
            )

            channel_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                self.guild_id,
                self.channel_id,
                self.user_id,
                self.channel_name,
                "channel",
            )
            server_lists.append(
                {
                    "_id": channel_list.get("_id"),
                    "label": "Built-in",
                    "name": TodoFunctions.display_list_name(channel_list, "This Channel"),
                }
            )

            custom_server_lists = await asyncio.to_thread(
                TodoFunctions.list_custom_lists_for_scope,
                self.guild_id,
                self.user_id,
                self.channel_id,
                "channel",
                100,
            )
            for todo_list in custom_server_lists:
                server_lists.append(
                    {
                        "_id": todo_list.get("_id"),
                        "label": "Custom",
                        "name": TodoFunctions.display_list_name(todo_list, "Unnamed"),
                    }
                )

        if self.current_scope == "personal":
            personal_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                self.guild_id,
                self.channel_id,
                self.user_id,
                self.channel_name,
                "personal",
            )
            personal_lists.append(
                {
                    "_id": personal_list.get("_id"),
                    "label": "Built-in",
                    "name": TodoFunctions.display_list_name(personal_list, "Personal"),
                }
            )

            custom_personal_lists = await asyncio.to_thread(
                TodoFunctions.list_custom_lists_for_scope,
                self.guild_id,
                self.user_id,
                self.channel_id,
                "personal",
                100,
            )
            for todo_list in custom_personal_lists:
                personal_lists.append(
                    {
                        "_id": todo_list.get("_id"),
                        "label": "Custom",
                        "name": TodoFunctions.display_list_name(todo_list, "Unnamed"),
                    }
                )

        all_lists = [*server_lists, *personal_lists]
        item_counts = await asyncio.to_thread(
            TodoFunctions.count_items_for_lists,
            [entry.get("_id") for entry in all_lists],
        )
        for entry in all_lists:
            entry["item_count"] = item_counts.get(str(entry.get("_id") or ""), 0)

        self.entries = [
            *[self._normalize_entry("Server", entry) for entry in server_lists],
            *[self._normalize_entry("Personal", entry) for entry in personal_lists],
        ]
        self._sort_entries()
        self.total_pages = max(1, math.ceil(len(self.entries) / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))

    def focus_list(self, list_id: Any) -> None:
        target_id = str(list_id or "").strip()
        if not target_id:
            return

        for index, entry in enumerate(self.entries):
            if str(entry.get("_id") or "").strip() != target_id:
                continue
            self.page = (index // self.page_size) + 1
            return

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        self._build()
        await self.save_session()
        try:
            if self.message is not None:
                await self.message.edit(view=self, **self.payload())
                return
        except discord.NotFound:
            self.message = None
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "The list directory was updated, but refreshing it failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )

    async def _send_list_card(
        self,
        interaction: discord.Interaction,
        todo_list: Dict[str, Any],
    ) -> None:
        item_count = await asyncio.to_thread(
            TodoFunctions.count_items_on_list,
            todo_list.get("_id"),
        )
        result_view = TodoListDescriptionView(
            title="Todo List",
            description=(
                f"List: `{TodoFunctions.display_list_name(todo_list, 'List')}`\n"
                f"Items: `{item_count}`"
            ),
            color=discord.Colour.blurple(),
            todo_list=todo_list,
            user_id=interaction.user.id,
        )
        await interaction.response.send_message(
            ephemeral=True,
            **result_view.response_payload(),
        )

    async def open_page_entry(
        self,
        interaction: discord.Interaction,
        slot_index: int,
    ) -> None:
        self.message = interaction.message
        entry = self._page_entry(slot_index)
        if entry is None:
            await interaction.response.defer()
            return
        selected_value = str(entry.get("_id") or "").strip()

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.fetch_todo_list_by_id,
                selected_value,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while opening that list.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not todo_list:
            await self.refresh_entries()
            await self.refresh_message(interaction)
            await handle_interaction_error(
                interaction,
                ValidationError("That list is no longer available.", ephemeral=True),
            )
            return

        await self._send_list_card(interaction, todo_list)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id is None or interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "Only the user who opened this list directory can use these controls.",
            ephemeral=True,
        )
        return False

    def _build(self) -> None:
        self.clear_items()
        if self.session_id is None:
            return

        from views.todo_list_directory_dynamic_items import (
            TodoDirectoryCreateButton,
            TodoDirectoryNextButton,
            TodoDirectoryOpenButton,
            TodoDirectoryPrevButton,
            TodoDirectorySortButton,
        )

        for slot_index in range(self.page_size):
            self.add_item(
                TodoDirectoryOpenButton(
                    self.session_id,
                    slot_index,
                    disabled=self._page_entry(slot_index) is None,
                )
            )

        self.add_item(
            TodoDirectoryPrevButton(
                self.session_id,
                disabled=self.page <= 1,
            )
        )
        self.add_item(
            TodoDirectoryNextButton(
                self.session_id,
                disabled=self.page >= self.total_pages,
            )
        )
        self.add_item(
            TodoDirectorySortButton(
                self.session_id,
                descending=self.sort_direction == "descending",
            )
        )
        self.add_item(TodoDirectoryCreateButton(self.session_id))
