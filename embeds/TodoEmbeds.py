import datetime
from typing import Optional, Union

import discord


class TodoEmbeds:
    @staticmethod
    def _format_due(due: Optional[Union[datetime.datetime, str]]) -> str:
        if due is None:
            return "Not set"

        if isinstance(due, str):
            try:
                due_dt = datetime.datetime.fromisoformat(due)
            except ValueError:
                return due
        else:
            due_dt = due

        return due_dt.strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def insert_todo_embed(
        name: str,
        description: Optional[str],
        due: Optional[Union[datetime.datetime, str]],
    ) -> dict:
        embed = discord.Embed(
            title="Todo Created",
            color=discord.Colour.green(),
        )
        embed.add_field(name="Name", value=name, inline=False)
        embed.add_field(
            name="Description", value=description or "Not set", inline=False
        )
        embed.add_field(name="Due", value=TodoEmbeds._format_due(due), inline=False)

        return {"embed": embed}

    @staticmethod
    def list_todos_embed(
        todos: list[dict],
        mode: str,
        sort: str,
    ) -> dict:
        embed = discord.Embed(
            title="Todo List",
            color=discord.Colour.blurple(),
        )

        if not todos:
            embed.description = "No todos found."
            return {"embed": embed}

        max_items = 25
        truncated = todos[:max_items]

        for index, todo in enumerate(truncated, start=1):
            name = str(todo.get("name") or "Untitled")
            description = todo.get("description") or "Not set"
            due = TodoEmbeds._format_due(todo.get("due"))
            embed.add_field(
                name=f"{index}. {name}",
                value=f"Description: {description}\nDue: {due}",
                inline=False,
            )

        extra_count = len(todos) - len(truncated)
        if extra_count > 0:
            embed.set_footer(text=f"+{extra_count} more not shown")

        embed.description = f"Mode: {mode} • Sort: {sort}"
        return {"embed": embed}
