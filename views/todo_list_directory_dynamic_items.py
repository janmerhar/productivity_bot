import discord
from discord.ext import commands
from services.visibility import inherit_ephemeral_from_interaction


async def register_todo_list_directory_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        TodoDirectoryOpenButton,
        TodoDirectoryPrevButton,
        TodoDirectoryNextButton,
        TodoDirectorySortButton,
        TodoDirectoryCreateButton,
    )


async def _ensure_view(
    interaction: discord.Interaction,
    *,
    session_id: str,
):
    from views.TodoListDirectoryView import TodoListDirectoryView

    view = await TodoListDirectoryView.from_session(interaction, session_id)
    if view is None:
        await interaction.response.send_message(
            "That todo list directory is no longer available. Run `/todo list browse` again.",
            ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
        )
        return None

    view.response_ephemeral = inherit_ephemeral_from_interaction(interaction, default=True)
    if not await view.interaction_check(interaction):
        return None
    return view


class TodoDirectoryOpenButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"tododir:open:(?P<session_id>[a-f0-9]+):(?P<slot>\d+)",
):
    def __init__(
        self,
        session_id: str,
        slot: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=str(slot + 1),
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=f"tododir:open:{session_id}:{slot}",
                disabled=disabled,
            )
        )
        self.session_id = session_id
        self.slot = slot

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TodoDirectoryOpenButton":
        del interaction
        return cls(
            match.group("session_id"),
            int(match.group("slot")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        await view.open_page_entry(interaction, self.slot)


class TodoDirectoryPrevButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"tododir:prev:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="◀️",
                row=1,
                custom_id=f"tododir:prev:{session_id}",
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
    ) -> "TodoDirectoryPrevButton":
        del interaction
        return cls(
            match.group("session_id"),
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
        view._build()
        await interaction.response.edit_message(view=view, **view.payload())
        await view.save_session()


class TodoDirectoryNextButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"tododir:next:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="▶️",
                row=1,
                custom_id=f"tododir:next:{session_id}",
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
    ) -> "TodoDirectoryNextButton":
        del interaction
        return cls(
            match.group("session_id"),
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
        view._build()
        await interaction.response.edit_message(view=view, **view.payload())
        await view.save_session()


class TodoDirectorySortButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"tododir:sort:(?P<session_id>[a-f0-9]+)",
):
    def __init__(
        self,
        session_id: str,
        *,
        descending: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                style=(
                    discord.ButtonStyle.primary
                    if descending
                    else discord.ButtonStyle.secondary
                ),
                emoji="🔽" if descending else "🔼",
                row=1,
                custom_id=f"tododir:sort:{session_id}",
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
    ) -> "TodoDirectorySortButton":
        del interaction
        emoji = str(getattr(item, "emoji", "") or "")
        return cls(
            match.group("session_id"),
            descending=emoji == "🔽",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        view.message = interaction.message
        view.sort_direction = (
            "descending" if view.sort_direction == "ascending" else "ascending"
        )
        view._sort_entries()
        view.page = 1
        view._build()
        await interaction.response.edit_message(view=view, **view.payload())
        await view.save_session()


class TodoDirectoryCreateButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"tododir:create:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="➕",
                row=1,
                custom_id=f"tododir:create:{session_id}",
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
    ) -> "TodoDirectoryCreateButton":
        del interaction, item
        return cls(match.group("session_id"))

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.TodoListDirectoryView import TodoListDirectoryCreateModal

        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        view.message = interaction.message
        await interaction.response.send_modal(TodoListDirectoryCreateModal(view))
