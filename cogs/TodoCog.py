import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds, TodoListView
from config.env import env


class TodoCog(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("TodoCog cog loaded")

    @app_commands.command(name="todo", description="Create a new to-do item")
    @app_commands.describe(
        name="Task name",
        description="Longer description for this task",
        due="Due date/time (natural language, same as /reminder)",
    )
    async def todo(
        self,
        interaction: discord.Interaction,
        name: str,
        description: Optional[str] = None,
        due: Optional[str] = None,
    ) -> None:
        if not name.strip():
            await interaction.response.send_message(
                ephemeral=True, content="Task name cannot be empty."
            )
            return

        await interaction.response.defer(ephemeral=True)

        try:
            document, due_dt = await asyncio.to_thread(
                TodoFunctions.insert_todo,
                interaction.user.id,
                interaction.channel_id,
                name,
                description,
                due,
            )
        except ValueError as exc:
            await interaction.followup.send(ephemeral=True, content=str(exc))
            return
        except Exception:
            await interaction.followup.send(
                ephemeral=True,
                content="Something went wrong while creating that todo.",
            )
            return

        await interaction.followup.send(
            ephemeral=True,
            **TodoEmbeds.insert_todo_embed(
                name=document["name"],
                description=document.get("description"),
                due=due_dt,
            ),
        )

    @app_commands.command(name="todolist", description="List todo items")
    @app_commands.describe(
        mode="Show all todos or only this channel",
        sort="Sort order for the list",
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
    )
    async def todolist(
        self,
        interaction: discord.Interaction,
        mode: Optional[app_commands.Choice[str]] = None,
        sort: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        mode_value = mode.value if mode else "channel"
        sort_value = sort.value if sort else "descending"

        await interaction.response.defer(ephemeral=True)

        try:
            todos = await asyncio.to_thread(
                TodoFunctions.list_todos,
                interaction.channel_id,
                mode_value,
                sort_value,
            )
        except Exception:
            await interaction.followup.send(
                ephemeral=True,
                content="Something went wrong while fetching todos.",
            )
            return

        payload = TodoEmbeds.list_todos_embed(
            todos=todos,
            mode=mode_value,
            sort=sort_value,
        )
        view = TodoListView(todos, mode_value, sort_value) if todos else None

        if view is None:
            await interaction.followup.send(ephemeral=True, **payload)
            return

        await interaction.followup.send(ephemeral=True, view=view, **payload)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(TodoCog(client), guilds=[discord.Object(env["GUILD_ID"])])
