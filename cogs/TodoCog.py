import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds
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


async def setup(client: commands.Bot) -> None:
    await client.add_cog(TodoCog(client), guilds=[discord.Object(env["GUILD_ID"])])
