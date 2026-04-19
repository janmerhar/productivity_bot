import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

import discord

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)
from services.visibility import inherit_ephemeral_from_interaction


ListConfirmCallback = Callable[[discord.Interaction], Awaitable[None]]


class TodoListConfirmModal(discord.ui.Modal):
    def __init__(
        self,
        *,
        title: str,
        description: str,
        on_confirm: ListConfirmCallback,
    ) -> None:
        super().__init__(title=(str(title or "").strip() or "Confirm Action")[:45])
        self.description = str(description or "").strip()
        self.on_confirm = on_confirm
        if self.description:
            self.add_item(discord.ui.TextDisplay(self.description))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.on_confirm(interaction)


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
        await interaction.response.defer(
            ephemeral=self.parent_view.response_ephemeral
        )

        todo_list = await self.parent_view.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=self.parent_view.response_ephemeral,
                ),
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
                ValidationError(
                    str(exc),
                    ephemeral=self.parent_view.response_ephemeral,
                    cause=exc,
                ),
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while renaming that list.",
                    ephemeral=self.parent_view.response_ephemeral,
                    cause=exc,
                ),
            )
            return

        if not updated_list:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "That list could not be renamed.",
                    ephemeral=self.parent_view.response_ephemeral,
                ),
            )
            return

        self.parent_view.todo_list = updated_list
        self.parent_view.list_id = str(updated_list.get("_id") or "").strip()
        self.parent_view.embed_title = "Todo List Updated"
        self.parent_view.embed_description = (
            f"Previous name: `{old_name}`\n"
            f"New name: `{updated_list.get('name') or 'List'}`"
        )
        self.parent_view.color = discord.Colour.blurple()
        self.parent_view._build()
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
        response_ephemeral: bool = True,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.embed_title = str(title or "").strip() or "Todo List"
        self.embed_description = str(description or "").strip()
        self.color = color or discord.Colour.blurple()
        self.todo_list = todo_list
        self.list_id = str((todo_list or {}).get("_id") or "").strip()
        self.user_id = user_id
        self.response_ephemeral = bool(response_ephemeral)
        self.message: Optional[discord.Message] = None
        self._build()

    @property
    def list_name(self) -> str:
        if not self.todo_list:
            return "List"
        return TodoFunctions.display_list_name(self.todo_list, "List")

    def _build(self) -> None:
        from views.todo_list_description_dynamic_items import (
            TodoListAddButton,
            TodoListClearButton,
            TodoListDeleteButton,
            TodoListRenameButton,
            TodoListShowButton,
        )

        has_list = bool(self.todo_list and self.todo_list.get("_id"))
        is_custom = has_list and (
            TodoFunctions.list_type(self.todo_list) == TodoFunctions._CUSTOM_LIST_TYPE
        )
        encoded_user_id = int(self.user_id or 0)

        self.clear_items()
        self.add_item(
            TodoListShowButton(
                self.list_id,
                encoded_user_id,
                disabled=not has_list,
            )
        )
        self.add_item(
            TodoListAddButton(
                self.list_id,
                encoded_user_id,
                disabled=not has_list,
            )
        )
        self.add_item(
            TodoListRenameButton(
                self.list_id,
                encoded_user_id,
                disabled=not is_custom,
            )
        )
        self.add_item(
            TodoListClearButton(
                self.list_id,
                encoded_user_id,
                disabled=not has_list,
            )
        )
        self.add_item(
            TodoListDeleteButton(
                self.list_id,
                encoded_user_id,
                disabled=not is_custom,
            )
        )

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
            ephemeral=inherit_ephemeral_from_interaction(
                interaction,
                default=self.response_ephemeral,
            ),
        )
        return False

    async def refresh_todo_list(self) -> Optional[Dict[str, Any]]:
        if not self.list_id:
            return None

        refreshed = await asyncio.to_thread(
            TodoFunctions.fetch_todo_list_by_id,
            self.list_id,
        )
        self.todo_list = refreshed
        self._build()
        return refreshed

    async def refresh_message(self, interaction: discord.Interaction) -> None:
        self._build()
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
                    ephemeral=self.response_ephemeral,
                ),
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "The list was updated, but refreshing the card failed.",
                    ephemeral=self.response_ephemeral,
                    cause=exc,
                ),
            )

    @staticmethod
    def _format_confirmation_description(
        *,
        action_text: str,
        list_name: str,
        item_count: int,
    ) -> str:
        return (
            f"{action_text}\n"
            f"List: `{list_name}`\n"
            f"Current items: `{item_count}`"
        )

    async def _run_clear_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=self.response_ephemeral)
        todo_list = await self.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=self.response_ephemeral,
                ),
            )
            return

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
                    ephemeral=self.response_ephemeral,
                    cause=exc,
                ),
            )
            return

        self.embed_title = "Todo List Cleared"
        self.embed_description = (
            f"List: `{TodoFunctions.display_list_name(todo_list, 'List')}`\n"
            f"Removed items: `{deleted_count}`"
        )
        self.color = discord.Colour.orange()
        await self.refresh_message(interaction)

    async def _run_delete_list(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=self.response_ephemeral)
        todo_list = await self.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=self.response_ephemeral,
                ),
            )
            return

        list_name = TodoFunctions.display_list_name(todo_list, "List")
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
                    ephemeral=self.response_ephemeral,
                    cause=exc,
                ),
            )
            return

        if not deleted:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "That list could not be deleted.",
                    ephemeral=self.response_ephemeral,
                ),
            )
            return

        self.todo_list = None
        self.embed_title = "Todo List Deleted"
        self.embed_description = (
            f"List: `{list_name}`\n"
            f"Removed items: `{deleted_count}`"
        )
        self.color = discord.Colour.red()
        self._build()
        self.stop()
        await self.refresh_message(interaction)
