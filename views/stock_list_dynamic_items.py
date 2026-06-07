import asyncio

import discord
from discord.ext import commands

from classes.DailyJobManager import DailyJobManager
from classes.PriceAlertFunctions import deactivate_alert
from services.error_reporting import handle_interaction_error
from services.visibility import inherit_ephemeral_from_interaction


async def register_stock_list_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        StockListSelectButton,
        StockListPrevButton,
        StockListNextButton,
        StockListRefreshButton,
        StockListManageButton,
        StockListDeleteButton,
    )


async def _ensure_view(
    interaction: discord.Interaction,
    *,
    session_id: str,
):
    from views.StockListItemsView import StockListItemsView

    view = await StockListItemsView.from_session(interaction, session_id)
    if view is None:
        await interaction.response.send_message(
            ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
            content="That stock list is no longer available. Run `/stock list` again.",
        )
        return None

    if not await view.interaction_check(interaction):
        return None
    return view


class StockListSelectButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"stocklist:select:(?P<session_id>[a-f0-9]+):(?P<slot>\d+)"
        r"(?::(?P<entry_type>[sa]):(?P<entry_id>[a-fA-F0-9]+))?"
    ),
):
    def __init__(
        self,
        session_id: str,
        slot: int,
        *,
        entry_type: str = "",
        entry_id: str = "",
        disabled: bool = False,
        selected: bool = False,
    ) -> None:
        cleaned_entry_type = str(entry_type or "").strip()
        cleaned_entry_id = str(entry_id or "").strip()
        custom_id = f"stocklist:select:{session_id}:{slot}"
        if cleaned_entry_type in {"s", "a"} and cleaned_entry_id:
            custom_id = f"{custom_id}:{cleaned_entry_type}:{cleaned_entry_id}"

        super().__init__(
            discord.ui.Button(
                label=str(slot + 1),
                style=(
                    discord.ButtonStyle.primary
                    if selected
                    else discord.ButtonStyle.secondary
                ),
                row=0,
                custom_id=custom_id,
                disabled=disabled,
            )
        )
        self.session_id = session_id
        self.slot = slot
        self.entry_type = cleaned_entry_type
        self.entry_id = cleaned_entry_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "StockListSelectButton":
        del interaction
        style = getattr(item, "style", discord.ButtonStyle.secondary)
        return cls(
            match.group("session_id"),
            int(match.group("slot")),
            entry_type=match.groupdict().get("entry_type") or "",
            entry_id=match.groupdict().get("entry_id") or "",
            disabled=getattr(item, "disabled", False),
            selected=style == discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        if self.entry_type and self.entry_id:
            selected = view.select_entry_by_reference(self.entry_type, self.entry_id)
            if not selected:
                await view._reload_entries()
                selected = view.select_entry_by_reference(self.entry_type, self.entry_id)
            if not selected:
                await interaction.response.defer(ephemeral=view.response_ephemeral)
                await view.refresh_message(interaction)
                return
        else:
            view._select_index(self.slot)
        await view.refresh_message(interaction)


class StockListPrevButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"stocklist:prev:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Prev",
                style=discord.ButtonStyle.secondary,
                row=1,
                custom_id=f"stocklist:prev:{session_id}",
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
    ) -> "StockListPrevButton":
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
        view._select_index(0)
        await view.refresh_message(interaction)


class StockListNextButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"stocklist:next:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Next",
                style=discord.ButtonStyle.secondary,
                row=1,
                custom_id=f"stocklist:next:{session_id}",
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
    ) -> "StockListNextButton":
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
        view._select_index(0)
        await view.refresh_message(interaction)


class StockListRefreshButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"stocklist:refresh:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Refresh",
                style=discord.ButtonStyle.secondary,
                row=1,
                custom_id=f"stocklist:refresh:{session_id}",
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
    ) -> "StockListRefreshButton":
        del interaction
        return cls(
            match.group("session_id"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        await interaction.response.defer(ephemeral=view.response_ephemeral)
        await view._reload_entries()
        await view.refresh_message(interaction)


class StockListManageButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"stocklist:manage:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Manage",
                style=discord.ButtonStyle.primary,
                row=2,
                custom_id=f"stocklist:manage:{session_id}",
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
    ) -> "StockListManageButton":
        del interaction
        return cls(
            match.group("session_id"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return
        await view.send_selected_item_actions(interaction)


class StockListDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"stocklist:delete:(?P<session_id>[a-f0-9]+)",
):
    def __init__(self, session_id: str, *, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Delete",
                style=discord.ButtonStyle.danger,
                row=2,
                custom_id=f"stocklist:delete:{session_id}",
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
    ) -> "StockListDeleteButton":
        del interaction
        return cls(
            match.group("session_id"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_view(interaction, session_id=self.session_id)
        if view is None:
            return

        current = view._selected_entry()
        if current is None:
            await interaction.response.send_message(
                ephemeral=view.response_ephemeral,
                content="No item selected.",
            )
            return

        try:
            if str(current.get("entry_type") or "") == "schedule":
                manager = DailyJobManager()
                deleted = await asyncio.to_thread(
                    manager.delete_job,
                    str(current.get("job_id") or ""),
                    current.get("channel_id"),
                    current.get("guild_id"),
                )
                message = "Schedule deleted." if deleted else "Schedule was not found."
            else:
                deleted = await asyncio.to_thread(
                    deactivate_alert,
                    str(current.get("alert_id") or ""),
                    view.user_id,
                    "stock",
                    view.guild_id,
                )
                message = "Alert deleted." if deleted else "Alert was not found."
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=view.response_ephemeral,
            )
            return

        await interaction.response.defer(ephemeral=view.response_ephemeral)
        await view._reload_entries()
        await view.refresh_message(interaction)
        await interaction.followup.send(
            ephemeral=view.response_ephemeral,
            content=message,
        )
