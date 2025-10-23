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

        if not quote or quote.get("price") is None:
            return {"content": f"• No data returned for `{symbol}`.", "embed": None}

        price = quote["price"]
        currency_code = (quote.get("currency") or "").upper()
        change_1d = quote.get("change1D_pct")

        def fmt_change(value):
            if value is None:
                return "—"
            return f"{value:+.2f}%"

        price_label = f"{price:,.2f}{f' {currency_code}' if currency_code else ''}"
        embed = discord.Embed(
            title=quote["symbol"].upper(),
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

        return {"content": None, "embed": embed}
