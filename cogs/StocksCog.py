import asyncio
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from embeds.StocksEmbeds import StocksEmbeds
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
    async def fetchStock(
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


async def setup(client):
    await client.add_cog(StocksCog(client))
