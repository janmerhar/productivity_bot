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
