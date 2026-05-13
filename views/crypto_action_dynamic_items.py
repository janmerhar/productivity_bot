import discord
from discord.ext import commands

from services.visibility import inherit_ephemeral_from_interaction


async def register_crypto_action_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        CryptoSetAlertButton,
        CryptoScheduleDailyCheckButton,
    )


def _build_view(
    coin_id: str,
    currency: str,
    *,
    response_ephemeral: bool,
):
    from views.CryptoActionView import CryptoActionView

    return CryptoActionView(
        coin_id,
        currency,
        response_ephemeral=response_ephemeral,
    )


class CryptoSetAlertButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"cryptoaction:alert:(?P<coin_id>[^:]+):(?P<currency>[^:]+)",
):
    def __init__(
        self,
        *,
        coin_id: str,
        currency: str,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Set Alert",
                style=discord.ButtonStyle.success,
                custom_id=f"cryptoaction:alert:{coin_id}:{currency}",
                disabled=disabled,
            )
        )
        self.coin_id = coin_id
        self.currency = currency

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "CryptoSetAlertButton":
        del interaction
        return cls(
            coin_id=match.group("coin_id"),
            currency=match.group("currency"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = _build_view(
            self.coin_id,
            self.currency,
            response_ephemeral=inherit_ephemeral_from_interaction(interaction),
        )
        await view.open_set_alert_modal(interaction)


class CryptoScheduleDailyCheckButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"cryptoaction:schedule:(?P<coin_id>[^:]+):(?P<currency>[^:]+)",
):
    def __init__(
        self,
        *,
        coin_id: str,
        currency: str,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Schedule Daily Check",
                style=discord.ButtonStyle.secondary,
                custom_id=f"cryptoaction:schedule:{coin_id}:{currency}",
                disabled=disabled,
            )
        )
        self.coin_id = coin_id
        self.currency = currency

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "CryptoScheduleDailyCheckButton":
        del interaction
        return cls(
            coin_id=match.group("coin_id"),
            currency=match.group("currency"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = _build_view(
            self.coin_id,
            self.currency,
            response_ephemeral=inherit_ephemeral_from_interaction(interaction),
        )
        await view.open_schedule_daily_check_modal(interaction)
