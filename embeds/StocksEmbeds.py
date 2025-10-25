from typing import List, Optional, Tuple

import discord

from classes.StocksFunctions import StocksFunctions


class StocksEmbeds:
    yahoo_color = 0x6001D2

    def stock_embed(self, ticker: str) -> dict:
        symbol = ticker.upper().strip()

        try:
            quote = StocksFunctions.fetchPrice(symbol)
        except Exception as exc:
            return {"content": f"• `{symbol}` lookup failed: {exc}", "embed": None}

        quote["symbol"] = quote.get("symbol") or symbol

        embed = self.stock_to_embed(quote)
        if embed is None:
            return {"content": f"• No data returned for `{symbol}`.", "embed": None}

        return {"content": None, "embed": embed}

    def stock_to_embed(self, quote: dict) -> Optional[discord.Embed]:
        if not quote:
            return None

        symbol = (quote.get("symbol") or "").upper()
        price = quote.get("price")

        if price is None:
            return None

        price = quote["price"]
        currency_code = (quote.get("currency") or "").upper()
        change_1d = quote.get("change1D_pct")

        def fmt_change(value):
            if value is None:
                return "—"
            return f"{value:+.2f}%"

        price_label = f"{price:,.2f}{f' {currency_code}' if currency_code else ''}"
        embed = discord.Embed(
            title=symbol or "Unknown",
            description=f"`{price_label}`",
            colour=self.yahoo_color,
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(name="1D", value=fmt_change(quote.get("change1D_pct")))
        embed.add_field(name="1W", value=fmt_change(quote.get("change1W_pct")))
        embed.add_field(name="1M", value=fmt_change(quote.get("change1M_pct")))

        prev_close = None
        if change_1d is not None:
            try:
                prev_close = price / (1 + change_1d / 100.0)
            except ZeroDivisionError:
                prev_close = None

        if prev_close is not None:
            change_abs = price - prev_close

            embed.add_field(
                name="Prev Close",
                value=f"{prev_close:,.2f}{f' {currency_code}' if currency_code else ''}",
                inline=True,
            )

            embed.add_field(
                name="Day Change",
                value=(
                    f"{change_abs:+.2f}{f' {currency_code}' if currency_code else ''}"
                    f" ({fmt_change(change_1d)})"
                ),
                inline=True,
            )

        embed.set_footer(text="Source: Yahoo Finance")

        return embed

    def daily_embeds(
        self, tickers: List[str]
    ) -> Tuple[List[discord.Embed], Optional[str]]:
        if not tickers:
            return [], "No stock tickers configured for this job."

        try:
            rows = StocksFunctions.fetchPrices(tickers)
        except Exception as exc:
            return [], f"Failed to fetch stock prices: {exc}"

        if not rows:
            return [], "No stock price data returned today."

        embeds: List[discord.Embed] = []
        for quote in rows:
            embed = self.stock_to_embed(quote)
            if embed is not None:
                embeds.append(embed)

        if not embeds:
            return [], "No stock price data returned today."

        return embeds[:10], None
