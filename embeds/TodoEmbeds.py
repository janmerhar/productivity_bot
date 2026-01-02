import asyncio
import datetime
import math
from typing import Optional, Union, List, Dict, Any

import discord

from classes.TodoFunctions import TodoFunctions


class TodoListView(discord.ui.View):
    def __init__(
        self,
        todos: List[Dict[str, Any]],
        mode: str,
        sort: str,
        page: int = 1,
        page_size: int = 5,
    ) -> None:
        super().__init__(timeout=300)
        self.todos = todos
        self.mode = mode
        self.sort = sort
        self.page_size = max(1, page_size)
        self.total_pages = max(1, math.ceil(len(todos) / self.page_size))
        self.page = max(1, min(page, self.total_pages))
        self._build()

    def _page_slice(self) -> List[Dict[str, Any]]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.todos[start:end]

    def _build(self) -> None:
        self.clear_items()

        start_index = (self.page - 1) * self.page_size
        page_items = self._page_slice()

        for offset, todo in enumerate(page_items, start=1):
            todo_id = str(todo.get("_id", ""))
            index = start_index + offset
            label = str(index)
            button = discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.secondary,
                emoji="✅",
                custom_id=f"todo_complete:{todo_id}",
                row=0,
            )

            async def _callback(
                interaction: discord.Interaction,
                todo_name: str = str(todo.get("name") or "todo"),
                todo_object_id: str = todo_id,
            ) -> None:
                await interaction.response.defer(ephemeral=True)
                updated = await asyncio.to_thread(
                    TodoFunctions.complete_todo, todo_object_id, interaction.guild_id
                )
                if not updated:
                    await interaction.followup.send(
                        ephemeral=True,
                        content=f"Couldn't complete '{todo_name}'.",
                    )
                    return
                await interaction.followup.send(
                    ephemeral=True,
                    content=f"Marked '{todo_name}' as done.",
                )

            button.callback = _callback
            self.add_item(button)

        prev_button = discord.ui.Button(
            label="",
            style=discord.ButtonStyle.secondary,
            emoji="◀️",
            disabled=self.page <= 1,
            row=1,
        )
        next_button = discord.ui.Button(
            label="",
            style=discord.ButtonStyle.secondary,
            emoji="▶️",
            disabled=self.page >= self.total_pages,
            row=1,
        )

        async def _prev_callback(interaction: discord.Interaction) -> None:
            if self.page <= 1:
                await interaction.response.defer(ephemeral=True)
                return
            self.page -= 1
            self._build()
            payload = TodoEmbeds.list_todos_embed(
                todos=self.todos,
                mode=self.mode,
                sort=self.sort,
                page=self.page,
                page_size=self.page_size,
            )
            await interaction.response.edit_message(view=self, **payload)

        async def _next_callback(interaction: discord.Interaction) -> None:
            if self.page >= self.total_pages:
                await interaction.response.defer(ephemeral=True)
                return
            self.page += 1
            self._build()
            payload = TodoEmbeds.list_todos_embed(
                todos=self.todos,
                mode=self.mode,
                sort=self.sort,
                page=self.page,
                page_size=self.page_size,
            )
            await interaction.response.edit_message(view=self, **payload)

        prev_button.callback = _prev_callback
        next_button.callback = _next_callback

        self.add_item(prev_button)
        self.add_item(next_button)


class TodoReminderView(discord.ui.View):
    def __init__(self, todo_id: str, todo_name: str) -> None:
        super().__init__(timeout=3600)
        self.todo_id = todo_id
        self.todo_name = todo_name

        button = discord.ui.Button(
            label="Complete",
            style=discord.ButtonStyle.success,
            custom_id=f"todo_reminder_complete:{todo_id}",
        )
        button.callback = self._on_complete
        self.add_item(button)

    async def _on_complete(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        updated = await asyncio.to_thread(
            TodoFunctions.complete_todo,
            self.todo_id,
            interaction.guild_id,
        )
        if not updated:
            await interaction.followup.send(
                ephemeral=True,
                content=f"Couldn't complete '{self.todo_name}'.",
            )
            return
        await interaction.followup.send(
            ephemeral=True,
            content=f"Marked '{self.todo_name}' as done.",
        )


class TodoEmbeds:
    @staticmethod
    def _number_emoji(value: int) -> str:
        digits = {
            "0": "0️⃣",
            "1": "1️⃣",
            "2": "2️⃣",
            "3": "3️⃣",
            "4": "4️⃣",
            "5": "5️⃣",
            "6": "6️⃣",
            "7": "7️⃣",
            "8": "8️⃣",
            "9": "9️⃣",
        }
        return "".join(digits.get(ch, ch) for ch in str(value))

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
        lines = []
        if description:
            lines.append(str(description))
        if due:
            lines.append(f"📅 {TodoEmbeds._format_due(due)}")

        embed.add_field(
            name=name,
            value="\n".join(lines) if lines else "No details",
            inline=False,
        )

        return {"embed": embed}

    @staticmethod
    def todo_reminder_payload(todo: Dict[str, Any]) -> dict:
        name = str(todo.get("name") or "Todo")
        description = todo.get("description")
        due = todo.get("due")
        user_id = todo.get("user_id")
        todo_id = str(todo.get("_id") or "")

        embed = discord.Embed(
            title="Todo Reminder",
            color=discord.Colour.orange(),
        )
        lines = []
        if description:
            lines.append(str(description))
        if due:
            lines.append(f"Due: {TodoEmbeds._format_due(due)}")

        embed.add_field(
            name=name,
            value="\n".join(lines) if lines else "No details",
            inline=False,
        )

        payload: Dict[str, Any] = {"embed": embed}
        if user_id:
            payload["content"] = f"<@{user_id}>"
        if todo_id:
            payload["view"] = TodoReminderView(todo_id, name)
        return payload

    @staticmethod
    def list_todos_embed(
        todos: list[dict],
        mode: str,
        sort: str,
        page: int = 1,
        page_size: int = 5,
    ) -> dict:
        embed = discord.Embed(
            title="Todo List",
            color=discord.Colour.blurple(),
        )

        total = len(todos)
        if total == 0:
            embed.description = "No todos found."
            return {"embed": embed}

        page_size = max(1, page_size)
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))

        start = (page - 1) * page_size
        end = start + page_size
        page_items = todos[start:end]

        for index, todo in enumerate(page_items, start=start + 1):
            name = str(todo.get("name") or "Untitled")
            description = todo.get("description")
            due_raw = todo.get("due")
            lines = []
            if description:
                lines.append(str(description))
            if due_raw:
                due = TodoEmbeds._format_due(due_raw)
                lines.append(f"📅 {due}")
            embed.add_field(
                name=f"{TodoEmbeds._number_emoji(index)} {name}",
                value="\n".join(lines),
                inline=False,
            )

        embed.description = f"Mode: {mode} • Sort: {sort}"
        embed.set_footer(text=f"Page {page}/{total_pages}")
        return {"embed": embed}
