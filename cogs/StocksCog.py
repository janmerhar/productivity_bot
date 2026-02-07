import asyncio
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from classes.PriceAlertFunctions import create_alert
from classes.StocksFunctions import StocksFunctions
from embeds.StocksEmbeds import StocksEmbeds
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


class StocksCog(commands.Cog):
    stock_group = app_commands.Group(name="stock", description="Stock quotes")

    def __init__(self, client):
        self.client = client

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("StocksCog cog loaded")

    # Commands

    # Naredi embed...
    @stock_group.command(name="quote", description="Get stock price")
    @app_commands.describe(
        ticker="Ticker symbol of the stock or ETF",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def fetch_stock(
        self,
        interaction: discord.Interaction,
        ticker: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        await interaction.edit_original_response(
            content=f"• Fetching `{ticker.upper()}` ⏳", embed=None
        )

        response = await asyncio.to_thread(StocksEmbeds.stock_embed, ticker)

        await interaction.edit_original_response(
            content=response.get("content"),
            embed=response.get("embed"),
        )

    @stock_group.command(name="alert", description="Set a stock price alert")
    @app_commands.describe(
        ticker="Ticker symbol of the stock or ETF",
        target_price="Alert target price",
        condition="Alert when market price crosses above or below target",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        condition=[
            app_commands.Choice(name="Crosses above target", value="above"),
            app_commands.Choice(name="Crosses below target", value="below"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def set_stock_alert(
        self,
        interaction: discord.Interaction,
        ticker: str,
        target_price: float,
        condition: app_commands.Choice[str],
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        symbol = ticker.strip().upper()
        if not symbol:
            raise ValidationError("Please provide a stock ticker.", ephemeral=ephemeral)
        if target_price <= 0:
            raise ValidationError(
                "Target price must be greater than 0.",
                ephemeral=ephemeral,
            )

        await interaction.response.defer(ephemeral=ephemeral)

        try:
            quote = await asyncio.to_thread(StocksFunctions.fetch_price, symbol)
        except Exception as exc:
            raise UserVisibleError(
                f"Failed to fetch `{symbol}` price data.",
                hint="Check the ticker and try again.",
                ephemeral=ephemeral,
                cause=exc,
            )

        currency_code = (quote.get("currency") or "").upper()
        if quote.get("price") is None:
            raise ValidationError(
                f"No live price data returned for `{symbol}`.",
                hint="Try another ticker or retry in a minute.",
                ephemeral=ephemeral,
            )

        rule = condition.value
        alert_id = await asyncio.to_thread(
            create_alert,
            asset_type="stock",
            symbol=symbol,
            target_price=target_price,
            condition=rule,
            currency=(quote.get("currency") or "").lower() or None,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
        )

        target_price_label = (
            f"{target_price:,.2f}{f' {currency_code}' if currency_code else ''}"
        )
        await interaction.followup.send(
            (
                f"Created stock alert `{alert_id}` for `{symbol}` when price is "
                f"`{rule}` `{target_price_label}`."
            ),
            ephemeral=ephemeral,
        )


async def setup(client):
    await client.add_cog(StocksCog(client))
