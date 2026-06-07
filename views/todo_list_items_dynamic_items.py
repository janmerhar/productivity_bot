import discord
from discord.ext import commands
from services.visibility import inherit_ephemeral_from_interaction


async def register_todo_list_items_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        TodoListItemInfoButton,
        TodoListItemsPrevButton,
        TodoListItemsNextButton,
        TodoListItemsAddButton,
        TodoListItemsOptionsButton,
    )


async def _ensure_view(
    interaction: discord.Interaction,
    *,
    session_id: str,
):
    from embeds.TodoEmbeds import TodoListItemsView

    view = await TodoListItemsView.from_session(interaction, session_id)
    if view is None:
        await interaction.response.send_message(
            ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
            content="That todo list is no longer available. Run `/todo list view` again.",
        )
        return None

    view.response_ephemeral = inherit_ephemeral_from_interaction(interaction, default=True)
    if view.user_id is not None and interaction.user.id != view.user_id:
        await interaction.response.send_message(
            ephemeral=view.response_ephemeral,
            content="Only the user who opened this list can manage it.",
        )
        return None

    return view


class TodoListItemInfoButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"todoitems:info:(?P<session_id>[a-f0-9]+):(?P<slot>\d+)"
        r"(?::(?P<item_id>[a-fA-F0-9]+))?"
    ),
):
    def __init__(
        self,
        session_id: str,
        slot: int,
        *,
        item_id: str = "",
        disabled: bool = False,
    ) -> None:
        cleaned_item_id = str(item_id or "").strip()
        custom_id = f"todoitems:info:{session_id}:{slot}"
        if cleaned_item_id:
            custom_id = f"{custom_id}:{cleaned_item_id}"

        super().__init__(
            discord.ui.Button(
                label=str(slot + 1),
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=custom_id,
                disabled=disabled,
            )
        )
        self.session_id = session_id
        self.slot = slot
        self.item_id = cleaned_item_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListItemInfoButton":
        del interaction
        return cls(
            match.group("session_id"),
            int(match.group("slot")),
            item_id=match.groupdict().get("item_id") or "",
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        if self.item_id:
            await view._open_item_details(interaction, {"_id": self.item_id})
            return
        await view._open_item_details(interaction, view._page_item(self.slot))


class TodoListItemsPrevButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todoitems:prev:(?P<session_id>[a-f0-9]+)(?::(?P<page>\d+))?",
):
    def __init__(
        self,
        session_id: str,
        *,
        page: int = 1,
        disabled: bool = False,
    ) -> None:
        self.page = max(1, int(page or 1))
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="\u25c0\ufe0f",
                row=1,
                custom_id=f"todoitems:prev:{session_id}:{self.page}",
                disabled=disabled,
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListItemsPrevButton":
        del interaction
        page = match.groupdict().get("page") or 1
        return cls(
            match.group("session_id"),
            page=int(page),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        if view.page <= 1:
            await interaction.response.defer(ephemeral=view.response_ephemeral)
            return
        view.page -= 1
        await view._safe_refresh_message(interaction)


class TodoListItemsNextButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todoitems:next:(?P<session_id>[a-f0-9]+)(?::(?P<page>\d+))?",
):
    def __init__(
        self,
        session_id: str,
        *,
        page: int = 1,
        disabled: bool = False,
    ) -> None:
        self.page = max(1, int(page or 1))
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="\u25b6\ufe0f",
                row=1,
                custom_id=f"todoitems:next:{session_id}:{self.page}",
                disabled=disabled,
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListItemsNextButton":
        del interaction
        page = match.groupdict().get("page") or 1
        return cls(
            match.group("session_id"),
            page=int(page),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        if view.page >= view.total_pages:
            await interaction.response.defer(ephemeral=view.response_ephemeral)
            return
        view.page += 1
        await view._safe_refresh_message(interaction)


class TodoListItemsAddButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todoitems:add:(?P<session_id>[a-f0-9]+)",
):
    def __init__(
        self,
        session_id: str,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="\u2795",
                row=1,
                custom_id=f"todoitems:add:{session_id}",
                disabled=disabled,
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListItemsAddButton":
        del interaction
        return cls(
            match.group("session_id"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        await view.open_create_modal(
            interaction,
            source_message=interaction.message,
        )


class TodoListItemsOptionsButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"todoitems:options:(?P<session_id>[a-f0-9]+)",
):
    def __init__(
        self,
        session_id: str,
        *,
        active: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                style=(
                    discord.ButtonStyle.success
                    if active
                    else discord.ButtonStyle.secondary
                ),
                emoji="\U0001F50E",
                row=1,
                custom_id=f"todoitems:options:{session_id}",
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoListItemsOptionsButton":
        del interaction
        return cls(
            match.group("session_id"),
            active=getattr(item, "style", None) == discord.ButtonStyle.success,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        await view.open_options_modal(
            interaction,
            source_message=interaction.message,
        )
