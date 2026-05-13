import discord
from discord.ext import commands

from services.visibility import inherit_ephemeral_from_interaction


async def register_stock_action_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        StockSetAlertButton,
        StockScheduleDailyCheckButton,
    )


def _build_view(symbol: str, *, response_ephemeral: bool):
    from views.StockActionView import StockActionView

    return StockActionView(
        symbol,
        response_ephemeral=response_ephemeral,
    )


class StockSetAlertButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"stockaction:alert:(?P<symbol>[^:]+)",
):
    def __init__(self, *, symbol: str, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Set Alert",
                style=discord.ButtonStyle.success,
                custom_id=f"stockaction:alert:{symbol}",
                disabled=disabled,
            )
        )
        self.symbol = symbol

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "StockSetAlertButton":
        del interaction
        return cls(
            symbol=match.group("symbol"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = _build_view(
            self.symbol,
            response_ephemeral=inherit_ephemeral_from_interaction(interaction),
        )
        await view.open_set_alert_modal(interaction)


class StockScheduleDailyCheckButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"stockaction:schedule:(?P<symbol>[^:]+)",
):
    def __init__(self, *, symbol: str, disabled: bool = False) -> None:
        super().__init__(
            discord.ui.Button(
                label="Schedule Daily Check",
                style=discord.ButtonStyle.secondary,
                custom_id=f"stockaction:schedule:{symbol}",
                disabled=disabled,
            )
        )
        self.symbol = symbol

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "StockScheduleDailyCheckButton":
        del interaction
        return cls(
            symbol=match.group("symbol"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = _build_view(
            self.symbol,
            response_ephemeral=inherit_ephemeral_from_interaction(interaction),
        )
        await view.open_schedule_daily_check_modal(interaction)
