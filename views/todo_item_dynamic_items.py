import asyncio
from typing import Optional

import discord
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from services.error_reporting import handle_interaction_error
from services.visibility import inherit_ephemeral_from_interaction

_ACTION_BUTTONS = {
    "progress": (
        "complete_todo",
        "\N{WHITE HEAVY CHECK MARK}",
        discord.ButtonStyle.success,
    ),
    "edit": ("edit_todo", "\N{LOWER RIGHT PENCIL}", discord.ButtonStyle.secondary),
    "assign": (
        "assign_to_user",
        "\N{BUSTS IN SILHOUETTE}",
        discord.ButtonStyle.secondary,
    ),
    "duplicate": ("duplicate_todo", "\N{PAGE FACING UP}", discord.ButtonStyle.primary),
    "delete": ("delete_todo", "\N{WASTEBASKET}", discord.ButtonStyle.danger),
}


async def register_todo_item_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(TodoItemActionButton)


def _bool_flag(value: bool) -> str:
    return "1" if value else "0"


def _parse_bool_flag(value: str) -> bool:
    return str(value or "").strip() == "1"


class TodoItemActionButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"todoitem:(?P<action>progress|edit|assign|duplicate|delete):"
        r"(?P<item_id>[0-9a-f]{24}):(?P<ephemeral>[01])"
    ),
):
    def __init__(
        self,
        action: str,
        item_id: str,
        response_ephemeral: bool,
        *,
        button: Optional[discord.ui.Button] = None,
    ) -> None:
        if action not in _ACTION_BUTTONS:
            raise ValueError(f"Unsupported todo item action: {action}")

        _, emoji, style = _ACTION_BUTTONS[action]
        custom_id = (
            f"todoitem:{action}:{item_id}:{_bool_flag(response_ephemeral)}"
        )
        if button is None:
            button = discord.ui.Button(
                emoji=emoji,
                style=style,
                row=0,
                custom_id=custom_id,
            )
        else:
            button.custom_id = custom_id

        super().__init__(button)
        self.action = action
        self.item_id = item_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoItemActionButton":
        del interaction
        if not isinstance(item, discord.ui.Button):
            raise TypeError("Todo item actions must be buttons.")
        return cls(
            match.group("action"),
            match.group("item_id"),
            _parse_bool_flag(match.group("ephemeral")),
            button=item,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from embeds.TodoEmbeds import TodoItemActionsView

        response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=self.response_ephemeral,
        )
        try:
            item = await asyncio.to_thread(
                TodoFunctions.fetch_todo,
                self.item_id,
                interaction.guild_id,
            )
            if item is None:
                await interaction.response.send_message(
                    content="That item no longer exists.",
                    ephemeral=response_ephemeral,
                )
                return

            todo_list = await asyncio.to_thread(
                TodoFunctions.fetch_todo_list_by_id,
                item.get("list_id"),
            )
            if todo_list is None:
                todo_list = {
                    "name": str(item.get("list_name") or "List"),
                    "scope": item.get("scope"),
                    "guild_id": item.get("guild_id"),
                    "channel_id": item.get("channel_id"),
                    "user_id": item.get("user_id"),
                }

            view = TodoItemActionsView(
                todo_list,
                item,
                response_ephemeral=response_ephemeral,
            )
            button_name = _ACTION_BUTTONS[self.action][0]
            await getattr(view, button_name).callback(interaction)
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=response_ephemeral,
            )
