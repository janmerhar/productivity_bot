import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds, TodoListView
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


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
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def todo(
        self,
        interaction: discord.Interaction,
        name: str,
        description: Optional[str] = None,
        due: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
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
        mode="Show all todos or only this channel",
        sort="Sort order for the list",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="All", value="all"),
            app_commands.Choice(name="Channel", value="channel"),
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

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            todos = await asyncio.to_thread(
                TodoFunctions.list_todos,
                interaction.guild_id,
                interaction.channel_id,
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
        view = TodoListView(todos, mode_value, sort_value) if todos else None

        if view is None:
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return

        await interaction.followup.send(ephemeral=ephemeral, view=view, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(TodoCog(client))


