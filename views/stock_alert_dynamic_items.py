import asyncio
from typing import Optional

import discord
from discord.ext import commands

from classes.PriceAlertFunctions import deactivate_alert, set_alert_paused
from services.visibility import inherit_ephemeral_from_interaction


async def register_stock_alert_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        StockAlertEditButton,
        StockAlertToggleButton,
        StockAlertDeleteButton,
    )


def _guild_value(guild_id: Optional[int]) -> int:
    return int(guild_id or 0)


def _parse_guild_id(raw_value: str) -> Optional[int]:
    parsed = int(raw_value)
    return parsed or None


async def _ensure_allowed(
    interaction: discord.Interaction,
    *,
    user_id: int,
    response_ephemeral: bool,
) -> bool:
    if interaction.user.id == user_id:
        return True

    await interaction.response.send_message(
        ephemeral=response_ephemeral,
        content="Only the user who opened this alert can manage it.",
    )
    return False


async def _build_view(
    interaction: discord.Interaction,
    *,
    alert_id: str,
    user_id: int,
    guild_id: Optional[int],
    response_ephemeral: bool,
):
    from views.StockAlertActionView import StockAlertActionView

    view = StockAlertActionView(
        alert_id=alert_id,
        user_id=user_id,
        guild_id=guild_id,
        response_ephemeral=response_ephemeral,
    )
    view.message = interaction.message
    await view.initialize()
    return view


class StockAlertEditButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"stockalert:edit:(?P<alert_id>[^:]+):(?P<user_id>\d+):(?P<guild_id>\d+)"
    ),
):
    def __init__(
        self,
        alert_id: str,
        user_id: int,
        guild_id: Optional[int],
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                row=0,
                custom_id=(
                    f"stockalert:edit:{alert_id}:{user_id}:{_guild_value(guild_id)}"
                ),
                disabled=disabled,
            )
        )
        self.alert_id = alert_id
        self.user_id = user_id
        self.guild_id = guild_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "StockAlertEditButton":
        return cls(
            match.group("alert_id"),
            int(match.group("user_id")),
            _parse_guild_id(match.group("guild_id")),
            inherit_ephemeral_from_interaction(interaction),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.StockAlertActionView import StockAlertEditModal

        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        view = await _build_view(
            interaction,
            alert_id=self.alert_id,
            user_id=self.user_id,
            guild_id=self.guild_id,
            response_ephemeral=self.response_ephemeral,
        )
        if view.alert is None:
            await interaction.response.send_message(
                ephemeral=self.response_ephemeral,
                content="That alert is no longer active.",
            )
            return

        await interaction.response.send_modal(StockAlertEditModal(view, view.alert))


class StockAlertToggleButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"stockalert:toggle:(?P<alert_id>[^:]+):(?P<user_id>\d+):(?P<guild_id>\d+)"
    ),
):
    def __init__(
        self,
        alert_id: str,
        user_id: int,
        guild_id: Optional[int],
        response_ephemeral: bool,
        *,
        paused: bool = False,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Resume" if paused else "Pause",
                style=(
                    discord.ButtonStyle.success
                    if paused
                    else discord.ButtonStyle.secondary
                ),
                row=0,
                custom_id=(
                    f"stockalert:toggle:{alert_id}:{user_id}:{_guild_value(guild_id)}"
                ),
                disabled=disabled,
            )
        )
        self.alert_id = alert_id
        self.user_id = user_id
        self.guild_id = guild_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "StockAlertToggleButton":
        return cls(
            match.group("alert_id"),
            int(match.group("user_id")),
            _parse_guild_id(match.group("guild_id")),
            inherit_ephemeral_from_interaction(interaction),
            paused=str(getattr(item, "label", "") or "").strip().lower() == "resume",
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        view = await _build_view(
            interaction,
            alert_id=self.alert_id,
            user_id=self.user_id,
            guild_id=self.guild_id,
            response_ephemeral=self.response_ephemeral,
        )

        await interaction.response.defer(ephemeral=self.response_ephemeral)
        if view.alert is None:
            await interaction.followup.send(
                ephemeral=self.response_ephemeral,
                content="That alert is no longer active.",
            )
            return

        currently_paused = bool(view.alert.get("paused"))
        changed = await asyncio.to_thread(
            set_alert_paused,
            self.alert_id,
            self.user_id,
            not currently_paused,
            asset_type="stock",
            guild_id=self.guild_id,
        )
        if not changed:
            await interaction.followup.send(
                ephemeral=self.response_ephemeral,
                content="That alert could not be updated.",
            )
            return

        await view.refresh_state()
        await view.refresh_message()
        await interaction.followup.send(
            ephemeral=self.response_ephemeral,
            content="Alert resumed." if currently_paused else "Alert paused.",
        )


class StockAlertDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"stockalert:delete:(?P<alert_id>[^:]+):(?P<user_id>\d+):(?P<guild_id>\d+)"
    ),
):
    def __init__(
        self,
        alert_id: str,
        user_id: int,
        guild_id: Optional[int],
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Delete",
                style=discord.ButtonStyle.danger,
                row=0,
                custom_id=(
                    f"stockalert:delete:{alert_id}:{user_id}:{_guild_value(guild_id)}"
                ),
                disabled=disabled,
            )
        )
        self.alert_id = alert_id
        self.user_id = user_id
        self.guild_id = guild_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "StockAlertDeleteButton":
        return cls(
            match.group("alert_id"),
            int(match.group("user_id")),
            _parse_guild_id(match.group("guild_id")),
            inherit_ephemeral_from_interaction(interaction),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        view = await _build_view(
            interaction,
            alert_id=self.alert_id,
            user_id=self.user_id,
            guild_id=self.guild_id,
            response_ephemeral=self.response_ephemeral,
        )

        await interaction.response.defer(ephemeral=self.response_ephemeral)
        deleted = await asyncio.to_thread(
            deactivate_alert,
            self.alert_id,
            self.user_id,
            "stock",
            self.guild_id,
        )
        if not deleted:
            await interaction.followup.send(
                ephemeral=self.response_ephemeral,
                content="That alert was not found.",
            )
            return

        await view.refresh_state()
        await view.refresh_message()
        await interaction.followup.send(
            ephemeral=self.response_ephemeral,
            content="Alert deleted.",
        )
