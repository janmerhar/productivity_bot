import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from classes.CryptoFunctions import CryptoFunctions
from cogs.CryptoEmbeds import CryptoEmbeds


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
    )
    async def fetchCrypto(
        self, interaction: discord.Interaction, ticker: str, currency: str = "usd"
    ):
        await interaction.response.send_message(
            f"• Fetching `{ticker.upper()}` in {currency.upper()} ⏳"
        )

        async def _update_message():
            try:
                results = await asyncio.to_thread(
                    CryptoFunctions.fetchPrices,
                    [ticker.lower()],
                    currency.lower(),
                )
            except Exception as exc:
                await interaction.edit_original_response(
                    content=f"• `{ticker.upper()}` lookup failed: {exc}", embed=None
                )
                return

            if not results:
                await interaction.edit_original_response(
                    content=f"• No data returned for `{ticker.upper()}` in {currency.upper()}.",
                    embed=None,
                )
                return

            coin = results[0]
            embed_param = CryptoEmbeds.price_embed(coin, currency)
            await interaction.edit_original_response(content=None, **embed_param)

        asyncio.create_task(_update_message())


async def setup(client):
    await client.add_cog(
        CryptoCog(client), guilds=[discord.Object(id=864242668066177044)]
    )
