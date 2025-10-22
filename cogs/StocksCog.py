import asyncio
import discord
from discord.ext import commands
from discord import app_commands
from classes.StocksFunctions import StocksFunctions


class StocksCog(commands.Cog):
    def __init__(self, client):
        self.client = client

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

        try:
            quote = await asyncio.to_thread(StocksFunctions.fetchPrice, ticker.upper())
        except Exception as exc:
            await interaction.edit_original_response(
                content=f"• `{ticker.upper()}` lookup failed: {exc}", embed=None
            )
            return

        if not quote or quote.get("price") is None:
            await interaction.edit_original_response(
                content=f"• No data returned for `{ticker.upper()}`.", embed=None
            )
            return

        price = quote["price"]
        currency = quote.get("currency") or ""
        currency_code = currency.upper()
        change_1d = quote.get("change1D_pct")

        colour = 0x57F287 if change_1d is None or change_1d >= 0 else 0xED4245

        price_label = f"{price:,.2f}{f' {currency_code}' if currency_code else ''}"
        embed = discord.Embed(
            title=quote["symbol"].upper(),
            description=f"`{price_label}`",
            colour=colour,
            timestamp=discord.utils.utcnow(),
        )

        def fmt_change(value):
            if value is None:
                return "—"
            return f"{value:+.2f}%"

        embed.add_field(name="1D", value=fmt_change(quote.get("change1D_pct")))
        embed.add_field(name="1W", value=fmt_change(quote.get("change1W_pct")))
        embed.add_field(name="1M", value=fmt_change(quote.get("change1M_pct")))

        prev_close = None
        change_abs = None
        if change_1d is not None:
            try:
                prev_close = price / (1 + change_1d / 100.0)
            except ZeroDivisionError:
                prev_close = None

        if prev_close is not None:
            change_abs = price - prev_close

        if prev_close is not None:
            embed.add_field(
                name="Prev Close",
                value=f"{prev_close:,.2f}{f' {currency_code}' if currency_code else ''}",
                inline=True,
            )

        if change_abs is not None:
            embed.add_field(
                name="Day Change",
                value=(
                    f"{change_abs:+.2f}{f' {currency_code}' if currency_code else ''}"
                    f" ({fmt_change(change_1d)})"
                ),
                inline=True,
            )

        embed.set_footer(text="Source: Yahoo Finance")

        await interaction.edit_original_response(content=None, embed=embed)


async def setup(client):
    await client.add_cog(
        StocksCog(client), guilds=[discord.Object(id=864242668066177044)]
    )
