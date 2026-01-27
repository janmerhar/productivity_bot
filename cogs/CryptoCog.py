import asyncio
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

from embeds.CryptoEmbeds import CryptoEmbeds
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


class CryptoCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("CryptoCog cog loaded")

    # Commands

    # Naredi embed...
    @app_commands.command(name="crypto", description="Get cryptocurrency price")
    @app_commands.describe(
        ticker="Ticker symbol of the cryptocurrency",
        currency="Currency to compare against",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def fetchCrypto(
        self,
        interaction: discord.Interaction,
        ticker: str,
        currency: str = "usd",
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
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

        await interaction.edit_original_response(
            content=response.get("content"),
            embed=response.get("embed"),
        )


async def setup(client):
    await client.add_cog(CryptoCog(client))
