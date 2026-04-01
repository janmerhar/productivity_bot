import asyncio
from typing import Any, Dict, Optional

import discord

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds, TodoListItemsView
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)


class TodoListRenameModal(discord.ui.Modal):
    def __init__(self, parent_view: "TodoListDescriptionView") -> None:
        super().__init__(title="Rename Todo List")
        self.parent_view = parent_view
        self.name_input = discord.ui.TextInput(
            label="List name",
            required=True,
            default=parent_view.list_name[:80],
            max_length=80,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        todo_list = await self.parent_view.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError("That list is no longer available.", ephemeral=True),
            )
            return

        old_name = str(todo_list.get("name") or "List")
        try:
            updated_list = await asyncio.to_thread(
                TodoFunctions.rename_todo_list,
                todo_list.get("_id"),
                str(self.name_input.value or ""),
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
                    "Something went wrong while renaming that list.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not updated_list:
            await handle_interaction_error(
                interaction,
                UserVisibleError("That list could not be renamed.", ephemeral=True),
            )
            return

        self.parent_view.todo_list = updated_list
        self.parent_view.embed_title = "Todo List Updated"
        self.parent_view.embed_description = (
            f"Previous name: `{old_name}`\n"
            f"New name: `{updated_list.get('name') or 'List'}`"
        )
        self.parent_view.color = discord.Colour.blurple()
        self.parent_view.sync_button_state()
        await self.parent_view.refresh_message(interaction)


class TodoListDescriptionView(discord.ui.View):
    def __init__(
        self,
        *,
        title: str,
        description: Optional[str] = None,
        color: Optional[discord.Colour] = None,
        todo_list: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
        timeout: float = 900,
    ) -> None:
        super().__init__(timeout=timeout)
        self.embed_title = str(title or "").strip() or "Todo List"
        self.embed_description = str(description or "").strip()
        self.color = color or discord.Colour.blurple()
        self.todo_list = todo_list
        self.user_id = user_id
        self.message: Optional[discord.Message] = None
        self.sync_button_state()

    @property
    def list_name(self) -> str:
        if not self.todo_list:
            return "List"
        return str(self.todo_list.get("name") or "List")

    def sync_button_state(self) -> None:
        has_list = bool(self.todo_list and self.todo_list.get("_id"))
        is_custom = has_list and (
            TodoFunctions.list_type(self.todo_list) == TodoFunctions._CUSTOM_LIST_TYPE
        )
        self.show_list.disabled = not has_list
        self.add_item.disabled = not has_list
        self.rename_list.disabled = not is_custom
        self.clear_list.disabled = not has_list
        self.delete_list.disabled = not is_custom

    def payload(self) -> dict:
        return TodoEmbeds.list_description_embed(
            title=self.embed_title,
            description=self.embed_description,
            color=self.color,
        )

    def response_payload(self) -> dict:
        payload = self.payload()
        payload["view"] = self
        return payload

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.user_id is None or interaction.user.id == self.user_id:
            return True

        await interaction.response.send_message(
            "Only the user who opened this list can manage it.",
            ephemeral=True,
        )
        return False

    async def refresh_todo_list(self) -> Optional[Dict[str, Any]]:
        if not self.todo_list or not self.todo_list.get("_id"):
            return None

        refreshed = await asyncio.to_thread(
            TodoFunctions.fetch_todo_list_by_id,
            self.todo_list.get("_id"),
        )
        self.todo_list = refreshed
        self.sync_button_state()
        return refreshed

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        self.sync_button_state()
        try:
            if self.message is not None:
                await self.message.edit(**self.response_payload())
                return
            await interaction.edit_original_response(**self.response_payload())
        except discord.NotFound:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "That todo list card is no longer available.",
                    ephemeral=True,
                ),
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "The list was updated, but refreshing the card failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )

    @discord.ui.button(emoji="📋", style=discord.ButtonStyle.secondary, row=0)
    async def show_list(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        todo_list = await self.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError("That list is no longer available.", ephemeral=True),
            )
            return

        try:
            items = await asyncio.to_thread(
                TodoFunctions.list_items_on_list,
                todo_list.get("_id"),
                "ascending",
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while loading that list.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not items:
            payload = TodoEmbeds.list_items_embed(todo_list, items, "ascending", "all")
            await interaction.response.send_message(ephemeral=True, **payload)
            return

        view = TodoListItemsView(
            todo_list=todo_list,
            items=items,
            sort="ascending",
            status_filter="all",
            user_id=interaction.user.id,
            view_scope="list",
            guild_id=interaction.guild_id,
        )
        await interaction.response.send_message(
            ephemeral=True,
            view=view,
            **view.payload(),
        )

    @discord.ui.button(emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def add_item(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        todo_list = await self.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError("That list is no longer available.", ephemeral=True),
            )
            return

        parent_view = TodoListItemsView(
            todo_list=todo_list,
            items=[],
            sort="ascending",
            status_filter="all",
            user_id=interaction.user.id,
            view_scope="list",
            guild_id=interaction.guild_id,
        )
        await parent_view.open_create_modal(
            interaction,
            source_message=None,
        )

    @discord.ui.button(emoji="✏️", style=discord.ButtonStyle.primary, row=0)
    async def rename_list(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        todo_list = await self.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError("That list is no longer available.", ephemeral=True),
            )
            return

        await interaction.response.send_modal(TodoListRenameModal(self))

    @discord.ui.button(emoji="🧹", style=discord.ButtonStyle.secondary, row=0)
    async def clear_list(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        todo_list = await self.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError("That list is no longer available.", ephemeral=True),
            )
            return

        await interaction.response.defer()
        try:
            deleted_count = await asyncio.to_thread(
                TodoFunctions.clear_todo_list_items,
                todo_list.get("_id"),
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while clearing that list.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        self.embed_title = "Todo List Cleared"
        self.embed_description = (
            f"List: `{todo_list.get('name') or 'List'}`\n"
            f"Removed items: `{deleted_count}`"
        )
        self.color = discord.Colour.orange()
        await self.refresh_message(interaction)

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def delete_list(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self.message = interaction.message
        todo_list = await self.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError("That list is no longer available.", ephemeral=True),
            )
            return

        list_name = str(todo_list.get("name") or "List")
        await interaction.response.defer()
        try:
            deleted, deleted_count = await asyncio.to_thread(
                TodoFunctions.delete_todo_list,
                todo_list.get("_id"),
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while deleting that list.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not deleted:
            await handle_interaction_error(
                interaction,
                UserVisibleError("That list could not be deleted.", ephemeral=True),
            )
            return

        self.todo_list = None
        self.embed_title = "Todo List Deleted"
        self.embed_description = (
            f"List: `{list_name}`\n"
            f"Removed items: `{deleted_count}`"
        )
        self.color = discord.Colour.red()
        self.sync_button_state()
        self.stop()
        await self.refresh_message(interaction)
