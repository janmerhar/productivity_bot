import asyncio
import discord
from discord.ext import commands
from discord import app_commands

from embeds.StocksEmbeds import StocksEmbeds
from config.env import env


class StocksCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.embeds = StocksEmbeds()

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("StocksCog cog loaded")

    # Commands

    # Naredi embed...
    @app_commands.command(name="stock", description="Get stock price")
    @app_commands.describe(ticker="Ticker symbol of the stock or ETF")
    async def fetchStock(self, interaction: discord.Interaction, ticker: str):
        await interaction.response.defer(thinking=True)
        await interaction.edit_original_response(
            content=f"• Fetching `{ticker.upper()}` ⏳", embed=None
        )

        response = await asyncio.to_thread(self.embeds.stock_embed, ticker)

        await interaction.edit_original_response(
            content=response.get("content"),
            embed=response.get("embed"),
        )


async def setup(client):
    await client.add_cog(StocksCog(client), guilds=[discord.Object(env["GUILD_ID"])])
