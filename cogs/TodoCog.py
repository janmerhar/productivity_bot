import asyncio
from typing import Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds, TodoListView
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


_SCOPE_CHOICES = [
    app_commands.Choice(name="Channel", value="channel"),
    app_commands.Choice(name="Personal", value="personal"),
]

_MAX_TITLE_LEN = 100
_MAX_DESC_LEN = 800


def _trim_text(text: str, limit: int) -> str:
    if limit <= 0:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _todo_from_message(message: discord.Message) -> Tuple[str, Optional[str]]:
    content = (message.content or "").strip()
    name_source = content.splitlines()[0].strip() if content else ""

    if not name_source:
        if message.attachments:
            name_source = f"Attachment from {message.author.display_name}"
        else:
            name_source = f"Message from {message.author.display_name}"

    name = _trim_text(name_source, _MAX_TITLE_LEN)

    description = _trim_text(content, _MAX_DESC_LEN) if content else None

    return name, description


async def _create_todo_from_message(
    interaction: discord.Interaction,
    message: discord.Message,
    scope: str,
) -> None:
    if not interaction.guild_id:
        raise UserVisibleError(
            "That action can only be used in a server.",
            ephemeral=True,
        )

    ephemeral = scope == "personal"
    name, description = _todo_from_message(message)
    if not name.strip():
        raise ValidationError("I couldn't extract a todo title.", ephemeral=ephemeral)

    await interaction.response.defer(ephemeral=ephemeral)

    try:
        document, _ = await asyncio.to_thread(
            TodoFunctions.insert_todo,
            interaction.guild_id,
            interaction.user.id,
            message.channel.id,
            name,
            description,
            None,
            scope,
        )
    except Exception as exc:
        raise UserVisibleError(
            "Something went wrong while creating that todo.",
            ephemeral=True,
            cause=exc,
        )

    payload = TodoEmbeds.insert_todo_embed(
        name=document["name"],
        description=document.get("description"),
        due=None,
    )
    await interaction.followup.send(ephemeral=ephemeral, **payload)


@app_commands.context_menu(name="Add to Todo")
async def add_message_to_todo(
    interaction: discord.Interaction, message: discord.Message
) -> None:
    await _create_todo_from_message(interaction, message, "channel")


@app_commands.context_menu(name="Add to Personal Todo")
async def add_message_to_personal_todo(
    interaction: discord.Interaction, message: discord.Message
) -> None:
    await _create_todo_from_message(interaction, message, "personal")


class TodoCog(commands.Cog):
    todo_group = app_commands.Group(name="todo", description="Manage to-dos")

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("TodoCog cog loaded")

    @todo_group.command(name="create", description="Create a new to-do item")
    @app_commands.describe(
        name="Task name",
        description="Longer description for this task",
        due="Due date/time (natural language, same as /reminder)",
        scope="Where this todo should live",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(scope=_SCOPE_CHOICES, visibility=VISIBILITY_CHOICES)
    async def todo(
        self,
        interaction: discord.Interaction,
        name: str,
        description: Optional[str] = None,
        due: Optional[str] = None,
        scope: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = (
            scope.value
            if scope
            else ("personal" if interaction.guild_id is None else "channel")
        )
        default_visibility = "private" if scope_value == "personal" else "public"
        if interaction.guild_id is None:
            default_visibility = "private"
        ephemeral = resolve_visibility(visibility, default=default_visibility)
        if interaction.guild_id is None and scope_value != "personal":
            raise UserVisibleError(
                "That option is only available in servers.",
                ephemeral=ephemeral,
            )
        if not name.strip():
            raise ValidationError("Task name cannot be empty.", ephemeral=ephemeral)

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            document, due_dt = await asyncio.to_thread(
                TodoFunctions.insert_todo,
                interaction.guild_id,
                interaction.user.id,
                interaction.channel_id,
                name,
                description,
                due,
                scope_value,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while creating that todo.",
                ephemeral=ephemeral,
                cause=exc,
            )

        reminder_failed = False
        if due_dt:
            try:
                await asyncio.to_thread(
                    TodoFunctions.insert_todo_task,
                    document,
                    due_dt,
                )
            except Exception:
                reminder_failed = True

        payload = TodoEmbeds.insert_todo_embed(
            name=document["name"],
            description=document.get("description"),
            due=due_dt,
        )
        if reminder_failed:
            payload["content"] = (
                "Todo created, but I couldn't schedule the due reminder."
            )

        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @todo_group.command(name="list", description="List todo items")
    @app_commands.describe(
        mode="Show all todos, only this channel, or personal todos",
        sort="Sort order for the list",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Channel", value="channel"),
            app_commands.Choice(name="Personal", value="personal"),
        ],
        sort=[
            app_commands.Choice(name="Ascending", value="ascending"),
            app_commands.Choice(name="Descending", value="descending"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def todolist(
        self,
        interaction: discord.Interaction,
        mode: Optional[app_commands.Choice[str]] = None,
        sort: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        mode_value = mode.value if mode else "channel"
        sort_value = sort.value if sort else "descending"
        if interaction.guild_id is None:
            mode_value = mode.value if mode else "personal"
            if mode_value != "personal":
                raise UserVisibleError(
                    "That option is only available in servers.",
                    ephemeral=ephemeral,
                )

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            todos = await asyncio.to_thread(
                TodoFunctions.list_todos,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                mode_value,
                sort_value,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while fetching todos.",
                ephemeral=ephemeral,
                cause=exc,
            )

        payload = TodoEmbeds.list_todos_embed(
            todos=todos,
            mode=mode_value,
            sort=sort_value,
        )
        view = (
            TodoListView(todos, mode_value, sort_value, interaction.user.id)
            if todos
            else None
        )

        if view is None:
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return

        await interaction.followup.send(ephemeral=ephemeral, view=view, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(TodoCog(client))
    client.tree.add_command(add_message_to_todo)
    client.tree.add_command(add_message_to_personal_todo)
