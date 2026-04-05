import asyncio
import math
from typing import Any, Dict, List, Optional

import discord

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds
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
        timeout: float = 900,
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
        self.entries = [
            *[self._normalize_entry("Server", entry) for entry in server_lists],
            *[self._normalize_entry("Personal", entry) for entry in personal_lists],
        ]
        self.page_size = max(1, min(page_size, 5))
        self._sort_entries()
        self.total_pages = max(1, math.ceil(len(self.entries) / self.page_size))
        self.page = max(1, min(page, self.total_pages))
        self._sync_button_state()

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

    def _sync_button_state(self) -> None:
        self.previous_page.disabled = self.page <= 1
        self.next_page.disabled = self.page >= self.total_pages
        self.sort_lists.label = None
        self.sort_lists.emoji = (
            "🔽" if self.sort_direction == "descending" else "🔼"
        )
        self.sort_lists.style = (
            discord.ButtonStyle.primary
            if self.sort_direction == "descending"
            else discord.ButtonStyle.secondary
        )
        entry_buttons = [
            self.open_entry_1,
            self.open_entry_2,
            self.open_entry_3,
            self.open_entry_4,
            self.open_entry_5,
        ]
        for slot_index, button in enumerate(entry_buttons):
            button.disabled = self._page_entry(slot_index) is None

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
                    "item_count": await asyncio.to_thread(
                        TodoFunctions.count_items_on_list,
                        inbox_list.get("_id"),
                    ),
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
                    "item_count": await asyncio.to_thread(
                        TodoFunctions.count_items_on_list,
                        channel_list.get("_id"),
                    ),
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
                        "item_count": await asyncio.to_thread(
                            TodoFunctions.count_items_on_list,
                            todo_list.get("_id"),
                        ),
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
                    "item_count": await asyncio.to_thread(
                        TodoFunctions.count_items_on_list,
                        personal_list.get("_id"),
                    ),
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
                        "item_count": await asyncio.to_thread(
                            TodoFunctions.count_items_on_list,
                            todo_list.get("_id"),
                        ),
                    }
                )

        self.entries = [
            *[self._normalize_entry("Server", entry) for entry in server_lists],
            *[self._normalize_entry("Personal", entry) for entry in personal_lists],
        ]
        self._sort_entries()
        self.total_pages = max(1, math.ceil(len(self.entries) / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))
        self._sync_button_state()

    def focus_list(self, list_id: Any) -> None:
        target_id = str(list_id or "").strip()
        if not target_id:
            return

        for index, entry in enumerate(self.entries):
            if str(entry.get("_id") or "").strip() != target_id:
                continue
            self.page = (index // self.page_size) + 1
            self._sync_button_state()
            return

    async def refresh_message(self, interaction: discord.Interaction) -> None:
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
            return

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

    async def _open_page_entry(
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

    @discord.ui.button(label="1", style=discord.ButtonStyle.secondary, row=0)
    async def open_entry_1(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._open_page_entry(interaction, 0)

    @discord.ui.button(label="2", style=discord.ButtonStyle.secondary, row=0)
    async def open_entry_2(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._open_page_entry(interaction, 1)

    @discord.ui.button(label="3", style=discord.ButtonStyle.secondary, row=0)
    async def open_entry_3(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._open_page_entry(interaction, 2)

    @discord.ui.button(label="4", style=discord.ButtonStyle.secondary, row=0)
    async def open_entry_4(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._open_page_entry(interaction, 3)

    @discord.ui.button(label="5", style=discord.ButtonStyle.secondary, row=0)
    async def open_entry_5(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await self._open_page_entry(interaction, 4)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="◀️", row=1)
    async def previous_page(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if self.page <= 1:
            await interaction.response.defer()
            return

        self.page -= 1
        self._sync_button_state()
        await interaction.response.edit_message(view=self, **self.payload())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="▶️", row=1)
    async def next_page(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if self.page >= self.total_pages:
            await interaction.response.defer()
            return

        self.page += 1
        self._sync_button_state()
        await interaction.response.edit_message(view=self, **self.payload())

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🔼", row=1)
    async def sort_lists(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        self.sort_direction = (
            "descending"
            if self.sort_direction == "ascending"
            else "ascending"
        )
        self._sort_entries()
        self.page = 1
        self._sync_button_state()
        await interaction.response.edit_message(view=self, **self.payload())

    @discord.ui.button(
        style=discord.ButtonStyle.success,
        emoji="➕",
        row=1,
    )
    async def create_list(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        await interaction.response.send_modal(TodoListDirectoryCreateModal(self))
