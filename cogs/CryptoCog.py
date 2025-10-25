import asyncio
import discord
from discord.ext import commands
from discord import app_commands

from embeds.CryptoEmbeds import CryptoEmbeds
from config import env


class CryptoCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.embeds = CryptoEmbeds()

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
    )
    async def fetchCrypto(
        self, interaction: discord.Interaction, ticker: str, currency: str = "usd"
    ):
        await interaction.response.defer(thinking=True)
        await interaction.edit_original_response(
            content=f"• Fetching `{ticker.upper()}` in {currency.upper()} ⏳",
            embed=None,
        )

        response = await asyncio.to_thread(
            self.embeds.price_embed,
            ticker,
            currency,
        )

        await interaction.edit_original_response(
            content=response.get("content"),
            embed=response.get("embed"),
        )


async def setup(client):
    await client.add_cog(CryptoCog(client), guilds=[discord.Object(env["GUILD_ID"])])
