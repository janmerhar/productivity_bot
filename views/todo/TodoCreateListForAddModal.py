import asyncio
from typing import Any, Optional

import discord
from discord import app_commands

from classes.TodoFunctions import TodoFunctions
from services.discord_helpers import resolve_ephemeral_from_scope
from services.error_reporting import handle_interaction_error


class TodoCreateListForAddModal(discord.ui.Modal, title="Create New List"):
    def __init__(
        self,
        cog: Any,
        *,
        user_id: int,
        todo: str,
        description: Optional[str],
        due: Optional[str],
        status_value: str,
        assignee: Optional[str],
        notify_enabled: bool,
        visibility: Optional[app_commands.Choice[str]],
        locale_code: Optional[str],
        scope_value: str,
    ) -> None:
        super().__init__()
        self._cog = cog
        self._user_id = int(user_id)
        self._todo = todo
        self._description = description
        self._due = due
        self._status_value = status_value
        self._assignee = assignee
        self._notify_enabled = notify_enabled
        self._visibility = visibility
        self._locale_code = locale_code
        self._scope_value = scope_value

        self.name_input = discord.ui.TextInput(
            label="List name",
            placeholder="Work, Errands, Reading",
            required=True,
            max_length=TodoFunctions._MAX_LIST_NAME_LEN,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self._user_id:
            await interaction.response.send_message(
                "This form is only for the user who started the command.",
                ephemeral=True,
            )
            return

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.create_todo_list,
                interaction.guild_id,
                interaction.user.id,
                None,
                str(self.name_input.value or ""),
                self._scope_value,
            )
            ephemeral = resolve_ephemeral_from_scope(
                interaction.guild_id,
                self._scope_value,
                self._visibility,
            )
            await self._cog._start_item_add_flow(
                interaction=interaction,
                todo=self._todo,
                description=self._description,
                due=self._due,
                todo_list=todo_list,
                status_value=self._status_value,
                assignee=self._assignee,
                notify_enabled=self._notify_enabled,
                ephemeral=ephemeral,
                locale_code=self._locale_code,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc)
