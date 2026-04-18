import asyncio
from typing import List, Optional

import discord
from discord.ext import commands
from discord import app_commands

from classes.CryptoFunctions import CryptoFunctions
from classes.OpenAIFunctions import OpenAIFunctions
from classes.PriceAlertFunctions import create_alert
from config.env import settings
from embeds.CryptoEmbeds import CryptoEmbeds
from embeds.PriceAlertEmbeds import PriceAlertEmbeds
from services.discord_helpers import (
    alert_destination_autocomplete,
    normalize_alert_destination,
)
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import (
    VISIBILITY_CHOICES,
    VISIBILITY_DESC,
    resolve_visibility_for_context,
)
from views.CryptoActionView import CryptoActionView


class CryptoCog(commands.Cog):
    crypto_group = app_commands.Group(name="crypto", description="Crypto quotes")

    def __init__(self, client):
        self.client = client

    @staticmethod
    def _resolve_response_visibility(
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]],
        *,
        guild_default: str,
    ) -> bool:
        return resolve_visibility_for_context(
            interaction.guild_id,
            visibility,
            guild_default=guild_default,
        )

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("CryptoCog cog loaded")

    # Commands

    # Naredi embed...
    @crypto_group.command(name="price", description="Get cryptocurrency price")
    @app_commands.describe(
        ticker="Ticker symbol of the cryptocurrency",
        currency="Currency to compare against",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def fetch_crypto(
        self,
        interaction: discord.Interaction,
        ticker: str,
        currency: str = "usd",
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = self._resolve_response_visibility(
            interaction,
            visibility,
            guild_default="public",
        )
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        await interaction.edit_original_response(
            content=f"• Fetching `{ticker.upper()}` in {currency.upper()} ⏳",
            embed=None,
        )

        response = await asyncio.to_thread(
            CryptoEmbeds.price_embed,
            ticker,
            currency,
        )

        action_view = None
        if response.get("embed") is not None:
            action_view = CryptoActionView(
                ticker,
                currency,
                response_ephemeral=ephemeral,
            )

        await interaction.edit_original_response(
            content=response.get("content"),
            embed=response.get("embed"),
            view=action_view,
        )

    @crypto_group.command(name="alert", description="Set a crypto price alert")
    @app_commands.describe(
        ticker="CoinGecko coin id",
        target_price="Alert target price",
        currency="Currency to compare against",
        condition="Alert when market price crosses above or below target",
        expires_in="Optional: how long this alert should stay active (for example: 3 days, tomorrow 9am)",
        destination="Where to send the alert (current channel, server channels, or DMs)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        condition=[
            app_commands.Choice(name="Crosses above target", value="above"),
            app_commands.Choice(name="Crosses below target", value="below"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def set_crypto_alert(
        self,
        interaction: discord.Interaction,
        ticker: str,
        target_price: float,
        condition: app_commands.Choice[str],
        currency: str = "usd",
        expires_in: Optional[str] = None,
        destination: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = self._resolve_response_visibility(
            interaction,
            visibility,
            guild_default="private",
        )
        coin_id = ticker.strip().lower()
        vs_currency = currency.strip().lower()

        if not coin_id:
            raise ValidationError(
                "Please provide a crypto ticker.", ephemeral=ephemeral
            )
        if not vs_currency:
            raise ValidationError("Please provide a currency.", ephemeral=ephemeral)
        if target_price <= 0:
            raise ValidationError(
                "Target price must be greater than 0.",
                ephemeral=ephemeral,
            )

        expires_text = (expires_in or "").strip()

        try:
            destination_type, destination_channel_id, destination_label = (
                normalize_alert_destination(interaction, destination)
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

        timezone = None
        if expires_text:
            async def _continue_with_timezone(
                followup_interaction: discord.Interaction,
                resolved_timezone: str,
            ) -> None:
                await self._set_crypto_alert(
                    interaction=followup_interaction,
                    coin_id=coin_id,
                    target_price=target_price,
                    rule=condition.value,
                    vs_currency=vs_currency,
                    expires_text=expires_text,
                    destination_type=destination_type,
                    destination_channel_id=destination_channel_id,
                    destination_label=destination_label,
                    ephemeral=ephemeral,
                    timezone=resolved_timezone,
                )

            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/crypto alert`.",
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._set_crypto_alert(
            interaction=interaction,
            coin_id=coin_id,
            target_price=target_price,
            rule=condition.value,
            vs_currency=vs_currency,
            expires_text=expires_text,
            destination_type=destination_type,
            destination_channel_id=destination_channel_id,
            destination_label=destination_label,
            ephemeral=ephemeral,
            timezone=timezone,
        )

    async def _set_crypto_alert(
        self,
        interaction: discord.Interaction,
        coin_id: str,
        target_price: float,
        rule: str,
        vs_currency: str,
        expires_text: str,
        destination_type: str,
        destination_channel_id: Optional[int],
        destination_label: str,
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        try:
            results = await asyncio.to_thread(
                CryptoFunctions.fetch_prices,
                [coin_id],
                vs_currency,
                ("24h", "7d", "30d"),
            )
        except Exception as exc:
            raise UserVisibleError(
                f"Failed to fetch `{coin_id}` price data.",
                hint="Check the coin id and currency.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not results:
            raise ValidationError(
                f"No market data returned for `{coin_id}` in `{vs_currency}`.",
                hint="Use CoinGecko ids such as `bitcoin` or `ethereum`.",
                ephemeral=ephemeral,
            )

        coin = results[0]
        if coin.get("current_price") is None:
            raise ValidationError(
                f"No live price data returned for `{coin_id}`.",
                ephemeral=ephemeral,
            )

        expires_at = None
        if expires_text:
            api_key = settings.openai_api_key
            if not api_key:
                raise ValidationError(
                    "OpenAI API key is not configured.",
                    hint="Set `OPENAI_API_KEY` to use natural-language alert expiry.",
                    ephemeral=ephemeral,
                )

            expires_at = await asyncio.to_thread(
                OpenAIFunctions.parse_alert_expiration_datetime,
                expires_text,
                api_key=api_key,
                timezone=timezone,
            )
            if expires_at is None:
                raise ValidationError(
                    "I couldn't understand that alert expiry value.",
                    hint="Try `3 days`, `tomorrow 8pm`, or `in 2 hours`.",
                    ephemeral=ephemeral,
                )

        alert_id = await asyncio.to_thread(
            create_alert,
            asset_type="crypto",
            symbol=coin.get("id") or coin_id,
            target_price=target_price,
            condition=rule,
            currency=vs_currency,
            guild_id=interaction.guild_id,
            channel_id=destination_channel_id,
            destination_type=destination_type,
            expires_at=expires_at,
            user_id=interaction.user.id,
        )

        coin_name = coin.get("name") or coin_id
        await interaction.followup.send(
            ephemeral=ephemeral,
            **PriceAlertEmbeds.alert_created_embed(
                alert_id=alert_id,
                asset_label="Crypto",
                symbol_label=f"`{coin_name}` (`{coin.get('id') or coin_id}`)",
                condition=rule,
                target_price_label=f"{target_price:,.6f} {vs_currency.upper()}",
                destination_label=destination_label,
                expires_at=expires_at,
            ),
        )

    @set_crypto_alert.autocomplete("destination")
    async def crypto_alert_destination_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = "",
    ) -> List[app_commands.Choice[str]]:
        return alert_destination_autocomplete(interaction, current)


async def setup(client):
    await client.add_cog(CryptoCog(client))
