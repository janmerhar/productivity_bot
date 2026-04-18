import asyncio

import discord
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoListItemsView
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)
from services.visibility import inherit_ephemeral_from_interaction


async def register_todo_list_description_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        TodoListShowButton,
        TodoListAddButton,
        TodoListRenameButton,
        TodoListClearButton,
        TodoListDeleteButton,
    )


async def _build_view(
    interaction: discord.Interaction,
    *,
    list_id: str,
    user_id: int,
):
    from views.TodoListDescriptionView import TodoListDescriptionView

    todo_list = await asyncio.to_thread(
        TodoFunctions.fetch_todo_list_by_id,
        list_id,
    )
    description = ""
    if todo_list is not None:
        try:
            item_count = await asyncio.to_thread(
                TodoFunctions.count_items_on_list,
                todo_list.get("_id"),
            )
        except Exception:
            item_count = "?"
        description = (
            f"List: `{TodoFunctions.display_list_name(todo_list, 'List')}`\n"
            f"Items: `{item_count}`"
        )

    view = TodoListDescriptionView(
        title="Todo List",
        description=description,
        color=discord.Colour.blurple(),
        todo_list=todo_list,
        user_id=user_id or None,
        response_ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
    )
    view.list_id = str(list_id or "").strip()
    view.message = interaction.message
    return view


async def _ensure_allowed(view, interaction: discord.Interaction) -> bool:
    return await view.interaction_check(interaction)


class TodoListShowButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todolist:show:(?P<list_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        list_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="📋",
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=f"todolist:show:{list_id}:{user_id}",
                disabled=disabled,
            )
        )
        self.list_id = list_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListShowButton":
        del interaction
        return cls(
            match.group("list_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _build_view(
            interaction,
            list_id=self.list_id,
            user_id=self.user_id,
        )
        if not await _ensure_allowed(view, interaction):
            return

        todo_list = await view.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=view.response_ephemeral,
                ),
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
                    ephemeral=view.response_ephemeral,
                    cause=exc,
                ),
            )
            return

        items_view = TodoListItemsView(
            todo_list=todo_list,
            items=items,
            sort="ascending",
            status_filter="all",
            user_id=interaction.user.id,
            view_scope="list",
            guild_id=interaction.guild_id,
            response_ephemeral=view.response_ephemeral,
        )
        await items_view.ensure_session()
        await interaction.response.send_message(
            ephemeral=view.response_ephemeral,
            view=items_view,
            **items_view.payload(),
        )


class TodoListAddButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todolist:add:(?P<list_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        list_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="➕",
                style=discord.ButtonStyle.success,
                row=0,
                custom_id=f"todolist:add:{list_id}:{user_id}",
                disabled=disabled,
            )
        )
        self.list_id = list_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListAddButton":
        del interaction
        return cls(
            match.group("list_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _build_view(
            interaction,
            list_id=self.list_id,
            user_id=self.user_id,
        )
        if not await _ensure_allowed(view, interaction):
            return

        todo_list = await view.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=view.response_ephemeral,
                ),
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
            response_ephemeral=view.response_ephemeral,
        )
        await parent_view.open_create_modal(
            interaction,
            source_message=None,
        )


class TodoListRenameButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todolist:rename:(?P<list_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        list_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="✏️",
                style=discord.ButtonStyle.primary,
                row=0,
                custom_id=f"todolist:rename:{list_id}:{user_id}",
                disabled=disabled,
            )
        )
        self.list_id = list_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListRenameButton":
        del interaction
        return cls(
            match.group("list_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.TodoListDescriptionView import TodoListRenameModal

        view = await _build_view(
            interaction,
            list_id=self.list_id,
            user_id=self.user_id,
        )
        if not await _ensure_allowed(view, interaction):
            return

        todo_list = await view.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=view.response_ephemeral,
                ),
            )
            return

        await interaction.response.send_modal(TodoListRenameModal(view))


class TodoListClearButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todolist:clear:(?P<list_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        list_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="🧹",
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=f"todolist:clear:{list_id}:{user_id}",
                disabled=disabled,
            )
        )
        self.list_id = list_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListClearButton":
        del interaction
        return cls(
            match.group("list_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.TodoListDescriptionView import TodoListConfirmModal

        view = await _build_view(
            interaction,
            list_id=self.list_id,
            user_id=self.user_id,
        )
        if not await _ensure_allowed(view, interaction):
            return

        todo_list = await view.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=view.response_ephemeral,
                ),
            )
            return

        try:
            item_count = await asyncio.to_thread(
                TodoFunctions.count_items_on_list,
                todo_list.get("_id"),
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while preparing that confirmation.",
                    ephemeral=view.response_ephemeral,
                    cause=exc,
                ),
            )
            return

        description = view._format_confirmation_description(
            action_text="This will remove every item from this list.",
            list_name=TodoFunctions.display_list_name(todo_list, "List"),
            item_count=item_count,
        )
        await interaction.response.send_modal(
            TodoListConfirmModal(
                title="Clear Todo List",
                description=description,
                on_confirm=view._run_clear_list,
            )
        )


class TodoListDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todolist:delete:(?P<list_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        list_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="🗑️",
                style=discord.ButtonStyle.danger,
                row=0,
                custom_id=f"todolist:delete:{list_id}:{user_id}",
                disabled=disabled,
            )
        )
        self.list_id = list_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListDeleteButton":
        del interaction
        return cls(
            match.group("list_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.TodoListDescriptionView import TodoListConfirmModal

        view = await _build_view(
            interaction,
            list_id=self.list_id,
            user_id=self.user_id,
        )
        if not await _ensure_allowed(view, interaction):
            return

        todo_list = await view.refresh_todo_list()
        if todo_list is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That list is no longer available.",
                    ephemeral=view.response_ephemeral,
                ),
            )
            return

        list_name = TodoFunctions.display_list_name(todo_list, "List")
        try:
            item_count = await asyncio.to_thread(
                TodoFunctions.count_items_on_list,
                todo_list.get("_id"),
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while preparing that confirmation.",
                    ephemeral=view.response_ephemeral,
                    cause=exc,
                ),
            )
            return

        description = view._format_confirmation_description(
            action_text="This will permanently delete this custom list.",
            list_name=list_name,
            item_count=item_count,
        )
        await interaction.response.send_modal(
            TodoListConfirmModal(
                title="Delete Todo List",
                description=description,
                on_confirm=view._run_delete_list,
            )
        )
