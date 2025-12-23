from typing import List, Optional, Tuple

import discord

from classes.CryptoFunctions import CryptoFunctions


class CryptoEmbeds:
    @staticmethod
    def _fmt_change(value):
        if value is None:
            return "-"
        arrow = "▲" if value >= 0 else "▼"
        return f"{arrow} {value:.2f}%"

    @staticmethod
    def price_embed(ticker: str, currency: str = "usd") -> dict:
        coin_id = ticker.strip()
        vs_currency = currency.strip().lower()

        try:
            results = CryptoFunctions.fetchPrices(
                [coin_id.lower()], vs_currency, ("24h", "7d", "30d")
            )
        except Exception as exc:
            return {
                "content": f"• `{coin_id.upper()}` lookup failed: {exc}",
                "embed": None,
            }

        if not results:
            return {
                "content": f"• No data returned for `{coin_id.upper()}` in {currency.upper()}.",
                "embed": None,
            }

        coin = results[0]
        return {
            "content": None,
            "embed": CryptoEmbeds._build_price_embed(coin, vs_currency),
        }

    @staticmethod
    def coin_embed(coin_data: dict, currency: str) -> dict:
        return {
            "content": None,
            "embed": CryptoEmbeds._build_price_embed(coin_data, currency),
        }

    @staticmethod
    def _build_price_embed(coin_data: dict, currency: str) -> discord.Embed:
        coin_id = coin_data.get("id", "-")
        name = coin_data.get("name", coin_id)
        image_url = coin_data.get("image")
        price = coin_data.get("current_price")
        change_24h = coin_data.get("price_change_percentage_24h_in_currency")
        change_7d = coin_data.get("price_change_percentage_7d_in_currency")
        change_30d = coin_data.get("price_change_percentage_30d_in_currency")
        high_24h = coin_data.get("high_24h")
        low_24h = coin_data.get("low_24h")

        embed = discord.Embed(
            title=f":coin: {name}",
            description=f"`{coin_id}` market data",
            color=discord.Colour.orange(),
        )

        if image_url:
            embed.set_thumbnail(url=image_url)

        embed.add_field(
            name="Current Price",
            value=f"{price} {currency.upper()}" if price is not None else "-",
            inline=False,
        )
        embed.add_field(
            name="24h Change",
            value=CryptoEmbeds._fmt_change(change_24h),
            inline=True,
        )
        embed.add_field(
            name="7d Change",
            value=CryptoEmbeds._fmt_change(change_7d),
            inline=True,
        )
        embed.add_field(
            name="30d Change",
            value=CryptoEmbeds._fmt_change(change_30d),
            inline=True,
        )
        embed.add_field(
            name="24h High",
            value=f"{high_24h} {currency.upper()}" if high_24h is not None else "-",
            inline=True,
        )
        embed.add_field(
            name="24h Low",
            value=f"{low_24h} {currency.upper()}" if low_24h is not None else "-",
            inline=True,
        )

        return embed

    @staticmethod
    def daily_embeds(
        tickers: List[str],
        currency: str,
        change_periods: Tuple[str, ...],
    ) -> Tuple[List[discord.Embed], Optional[str]]:
        if not tickers:
            return [], "No crypto tickers configured for this job."

        try:
            rows = CryptoFunctions.fetchPrices(tickers, currency, change_periods)
        except Exception as exc:
            return [], f"Failed to fetch crypto prices: {exc}"

        if not rows:
            return [], "No crypto price data returned today."

        embeds: List[discord.Embed] = []
        for coin in rows:
            embed = CryptoEmbeds._build_price_embed(coin, currency)
            if embed is not None:
                embeds.append(embed)

        if not embeds:
            return [], "No crypto price data returned today."

        return embeds[:10], None
