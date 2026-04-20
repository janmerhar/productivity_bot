import discord
from discord.ext import commands


async def register_habit_list_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        HabitListShowButton,
        HabitListPrevButton,
        HabitListNextButton,
        HabitListAddButton,
        HabitListOptionsButton,
    )


async def _ensure_view(
    interaction: discord.Interaction,
    *,
    session_id: str,
):
    from views.HabitListView import HabitListView

    view = await HabitListView.from_session(interaction, session_id)
    if view is None:
        await interaction.response.send_message(
            "That habit list is no longer available. Run `/habit list` again.",
            ephemeral=True,
        )
        return None

    if not await view.interaction_check(interaction):
        return None
    return view


class HabitListShowButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habitlist:show:(?P<session_id>[a-f0-9]+):(?P<slot>\d+)",
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
                custom_id=f"habitlist:show:{session_id}:{slot}",
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
    ) -> "HabitListShowButton":
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
        await view.open_habit_details(interaction, view._page_item(self.slot))


class HabitListPrevButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habitlist:prev:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="\u25c0\ufe0f",
                row=1,
                custom_id=f"habitlist:prev:{session_id}",
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
    ) -> "HabitListPrevButton":
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
        await view._safe_refresh_message(interaction)


class HabitListNextButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habitlist:next:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                emoji="\u25b6\ufe0f",
                row=1,
                custom_id=f"habitlist:next:{session_id}",
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
    ) -> "HabitListNextButton":
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
        await view._safe_refresh_message(interaction)


class HabitListAddButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habitlist:add:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                emoji="\u2795",
                row=1,
                custom_id=f"habitlist:add:{session_id}",
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
    ) -> "HabitListAddButton":
        del interaction, item
        return cls(match.group("session_id"))

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        view.message = interaction.message
        await view.open_create_modal(
            interaction,
            source_message=interaction.message,
        )


class HabitListOptionsButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habitlist:options:(?P<session_id>[a-f0-9]+)",
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
                custom_id=f"habitlist:options:{session_id}",
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
    ) -> "HabitListOptionsButton":
        del interaction
        return cls(
            match.group("session_id"),
            active=getattr(item, "style", None) == discord.ButtonStyle.success,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        view.message = interaction.message
        await view.open_options_modal(
            interaction,
            source_message=interaction.message,
        )
