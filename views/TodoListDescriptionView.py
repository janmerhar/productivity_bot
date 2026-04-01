from typing import Optional

import discord

from embeds.TodoEmbeds import TodoEmbeds


class TodoListDescriptionView(discord.ui.View):
    def __init__(
        self,
        *,
        title: str,
        description: Optional[str] = None,
        color: Optional[discord.Colour] = None,
        timeout: float = 900,
    ) -> None:
        super().__init__(timeout=timeout)
        self.embed_title = str(title or "").strip() or "Todo List"
        self.embed_description = str(description or "").strip()
        self.color = color or discord.Colour.blurple()

    def payload(self) -> dict:
        return TodoEmbeds.list_description_embed(
            title=self.embed_title,
            description=self.embed_description,
            color=self.color,
        )

    def response_payload(self) -> dict:
        payload = self.payload()
        payload["view"] = self
        return payload
