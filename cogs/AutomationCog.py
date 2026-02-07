import asyncio
from typing import Optional

import discord
from discord.ext import commands, tasks

from classes.CryptoFunctions import CryptoFunctions
from classes.PriceAlertFunctions import (
    fetch_active_alerts,
    mark_triggered,
    should_trigger,
)
from classes.StocksFunctions import StocksFunctions
from embeds.CryptoEmbeds import CryptoEmbeds
from embeds.StocksEmbeds import StocksEmbeds
from services.discord_helpers import resolve_messageable_channel


class AutomationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._runner.start()

    @commands.Cog.listener()
    async def on_ready(self):
        print("AutomationCog cog loaded")

    def cog_unload(self) -> None:
        if self._runner.is_running():
            self._runner.cancel()

    @tasks.loop(minutes=1)
    async def _runner(self) -> None:
        await self._run_stock_alerts()
        await self._run_crypto_alerts()

    async def _run_stock_alerts(self) -> None:
        alerts = await asyncio.to_thread(
            fetch_active_alerts,
            "stock",
        )

        for alert in alerts:
            symbol = str(alert.get("symbol", "")).strip().upper()
            if not symbol:
                continue

            try:
                quote = await asyncio.to_thread(StocksFunctions.fetch_price, symbol)
            except Exception:
                continue

            current_price = quote.get("price")
            if current_price is None:
                continue

            if not should_trigger(alert, current_price):
                continue

            channel = await resolve_messageable_channel(
                self.bot, alert.get("channel_id")
            )
            if channel is None:
                continue

            alert_currency = (
                quote.get("currency") or alert.get("currency") or ""
            ).upper()
            current_label = (
                f"{current_price:,.2f}{f' {alert_currency}' if alert_currency else ''}"
            )
            target_price = float(alert.get("target_price", 0))
            target_label = (
                f"{target_price:,.2f}{f' {alert_currency}' if alert_currency else ''}"
            )
            condition = alert.get("condition", "above")
            mention = (
                f"<@{alert.get('user_id')}>" if alert.get("user_id") else "Stock alert"
            )
            embed = StocksEmbeds.stock_to_embed(quote)
            message = (
                f"{mention} stock alert: `{symbol}` is `{condition}` "
                f"`{target_label}`. Current price: `{current_label}`."
            )

            sent = await self._send_alert_message(
                channel=channel,
                content=message,
                embed=embed,
            )
            if not sent:
                continue

            await self._close_alert(alert_id=alert["_id"], current_price=current_price)

    async def _run_crypto_alerts(self) -> None:
        alerts = await asyncio.to_thread(
            fetch_active_alerts,
            "crypto",
        )

        for alert in alerts:
            coin_id = str(alert.get("symbol", "")).strip().lower()
            if not coin_id:
                continue

            currency = str(alert.get("currency") or "usd").strip().lower()
            if not currency:
                currency = "usd"

            try:
                results = await asyncio.to_thread(
                    CryptoFunctions.fetch_prices,
                    [coin_id],
                    currency,
                    ("24h", "7d", "30d"),
                )
            except Exception:
                continue

            if not results:
                continue

            coin = results[0]
            current_price = coin.get("current_price")
            if current_price is None:
                continue

            if not should_trigger(alert, current_price):
                continue

            channel = await resolve_messageable_channel(
                self.bot, alert.get("channel_id")
            )
            if channel is None:
                continue

            target_price = float(alert.get("target_price", 0))
            condition = alert.get("condition", "above")
            mention = (
                f"<@{alert.get('user_id')}>" if alert.get("user_id") else "Crypto alert"
            )
            embed = CryptoEmbeds.coin_embed(coin, currency).get("embed")
            message = (
                f"{mention} crypto alert: `{coin.get('name') or coin_id}` "
                f"is `{condition}` `{target_price:,.6f} {currency.upper()}`. "
                f"Current price: `{current_price:,.6f} {currency.upper()}`."
            )

            sent = await self._send_alert_message(
                channel=channel,
                content=message,
                embed=embed,
            )
            if not sent:
                continue

            await self._close_alert(alert_id=alert["_id"], current_price=current_price)

    async def _send_alert_message(
        self,
        channel: discord.abc.Messageable,
        content: str,
        embed: Optional[discord.Embed] = None,
    ) -> bool:
        try:
            await channel.send(content=content, embed=embed)
            return True
        except Exception:
            return False

    async def _close_alert(self, alert_id, current_price: float) -> None:
        await asyncio.to_thread(
            mark_triggered,
            alert_id,
            current_price,
        )

    @_runner.before_loop
    async def _before_runner(self) -> None:
        await self.bot.wait_until_ready()


async def setup(client: commands.Bot) -> None:
    await client.add_cog(AutomationCog(client))
