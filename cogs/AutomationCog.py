import asyncio
import logging
import time
from collections import defaultdict
from typing import Optional

import discord
from discord.ext import commands, tasks

from classes.CryptoFunctions import CryptoFunctions
from classes.PriceAlertFunctions import (
    delete_expired_alerts,
    fetch_active_alerts,
    mark_triggered,
    should_trigger,
)
from classes.StocksFunctions import StocksFunctions
from config.env import settings
from embeds.CryptoEmbeds import CryptoEmbeds
from embeds.StocksEmbeds import StocksEmbeds
from services.discord_helpers import resolve_alert_destination


class AutomationCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._alert_cleanup_interval_seconds = self._resolve_cleanup_interval_seconds()
        self._next_cleanup_at: dict[str, float] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        print("AutomationCog cog loaded")
        if not self._runner.is_running():
            self._runner.start()

    def cog_unload(self) -> None:
        if self._runner.is_running():
            self._runner.cancel()

    @tasks.loop(minutes=1)
    async def _runner(self) -> None:
        try:
            await self._run_stock_alerts()
        except Exception:
            logging.getLogger(__name__).exception("Failed to run stock alerts")

        try:
            await self._run_crypto_alerts()
        except Exception:
            logging.getLogger(__name__).exception("Failed to run crypto alerts")

    async def _run_stock_alerts(self) -> None:
        await self._cleanup_expired_alerts_if_due("stock")
        alerts = await asyncio.to_thread(
            fetch_active_alerts,
            "stock",
        )

        grouped_alerts: dict[str, list[dict]] = defaultdict(list)
        for alert in alerts:
            symbol = str(alert.get("symbol", "")).strip().upper()
            if not symbol:
                continue
            grouped_alerts[symbol].append(alert)

        for symbol, symbol_alerts in grouped_alerts.items():
            try:
                quote = await asyncio.to_thread(StocksFunctions.fetch_price, symbol)
            except Exception:
                continue

            current_price = quote.get("price")
            if current_price is None:
                continue

            for alert in symbol_alerts:
                if not should_trigger(alert, current_price):
                    continue

                destination = await resolve_alert_destination(
                    self.bot,
                    str(alert.get("destination_type") or "channel"),
                    alert.get("channel_id"),
                    alert.get("user_id"),
                )
                if destination is None:
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
                destination_type = str(alert.get("destination_type") or "channel")
                mention = ""
                if destination_type == "channel" and alert.get("user_id"):
                    mention = f"<@{alert.get('user_id')}> "
                embed = StocksEmbeds.stock_to_embed(quote)
                message = (
                    f"{mention}stock alert: `{symbol}` is `{condition}` "
                    f"`{target_label}`. Current price: `{current_label}`."
                )

                sent = await self._send_alert_message(
                    channel=destination,
                    content=message,
                    embed=embed,
                )
                if not sent:
                    continue

                await self._close_alert(
                    alert_id=alert["_id"],
                    current_price=current_price,
                )

    async def _run_crypto_alerts(self) -> None:
        await self._cleanup_expired_alerts_if_due("crypto")
        alerts = await asyncio.to_thread(
            fetch_active_alerts,
            "crypto",
        )

        grouped_alerts: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for alert in alerts:
            coin_id = str(alert.get("symbol", "")).strip().lower()
            if not coin_id:
                continue

            currency = str(alert.get("currency") or "usd").strip().lower()
            if not currency:
                currency = "usd"
            grouped_alerts[(coin_id, currency)].append(alert)

        for (coin_id, currency), coin_alerts in grouped_alerts.items():
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

            for alert in coin_alerts:
                if not should_trigger(alert, current_price):
                    continue

                destination = await resolve_alert_destination(
                    self.bot,
                    str(alert.get("destination_type") or "channel"),
                    alert.get("channel_id"),
                    alert.get("user_id"),
                )
                if destination is None:
                    continue

                target_price = float(alert.get("target_price", 0))
                condition = alert.get("condition", "above")
                destination_type = str(alert.get("destination_type") or "channel")
                mention = ""
                if destination_type == "channel" and alert.get("user_id"):
                    mention = f"<@{alert.get('user_id')}> "
                embed = CryptoEmbeds.coin_embed(coin, currency).get("embed")
                message = (
                    f"{mention}crypto alert: `{coin.get('name') or coin_id}` "
                    f"is `{condition}` `{target_price:,.6f} {currency.upper()}`. "
                    f"Current price: `{current_price:,.6f} {currency.upper()}`."
                )

                sent = await self._send_alert_message(
                    channel=destination,
                    content=message,
                    embed=embed,
                )
                if not sent:
                    continue

                await self._close_alert(
                    alert_id=alert["_id"],
                    current_price=current_price,
                )

    @staticmethod
    def _resolve_cleanup_interval_seconds() -> int:
        return max(1, settings.alert_expiry_cleanup_minutes) * 60

    async def _cleanup_expired_alerts_if_due(self, asset_type: str) -> None:
        now = time.monotonic()
        next_cleanup_at = self._next_cleanup_at.get(asset_type, 0.0)
        if now < next_cleanup_at:
            return

        self._next_cleanup_at[asset_type] = (
            now + self._alert_cleanup_interval_seconds
        )
        await asyncio.to_thread(delete_expired_alerts, asset_type)

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

async def setup(client: commands.Bot) -> None:
    await client.add_cog(AutomationCog(client))
