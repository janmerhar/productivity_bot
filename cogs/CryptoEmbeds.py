import discord


class CryptoEmbeds:
    def __init__(self):
        pass

    @staticmethod
    def price_embed(coingecko_element: dict, currency: str = "usd") -> dict:
        coin_id = coingecko_element.get("id", "-")
        name = coingecko_element.get("name", coin_id)
        image_url = coingecko_element.get("image")
        price = coingecko_element.get("current_price")
        change_24h = coingecko_element.get("price_change_percentage_24h_in_currency")
        change_7d = coingecko_element.get("price_change_percentage_7d_in_currency")
        change_30d = coingecko_element.get("price_change_percentage_30d_in_currency")
        high_24h = coingecko_element.get("high_24h")
        low_24h = coingecko_element.get("low_24h")

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
            value=f"{change_24h:.2f}%" if change_24h is not None else "-",
            inline=True,
        )
        embed.add_field(
            name="7d Change",
            value=f"{change_7d:.2f}%" if change_7d is not None else "-",
            inline=True,
        )
        embed.add_field(
            name="30d Change",
            value=f"{change_30d:.2f}%" if change_30d is not None else "-",
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

        return {"embed": embed}
