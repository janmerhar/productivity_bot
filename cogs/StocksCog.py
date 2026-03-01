import asyncio
from typing import List, Optional

import discord
from discord.ext import commands
from discord import app_commands

from classes.DailyJob import CronSchedule
from classes.DailyJobManager import DailyJobManager
from classes.OpenAIFunctions import OpenAIFunctions
from classes.PriceAlertFunctions import create_alert
from classes.StocksFunctions import StocksFunctions
from config.env import env
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.discord_helpers import (
    alert_destination_autocomplete,
    normalize_alert_destination,
)
from services.cron_schedule import (
    CronConversionError,
    is_valid_cron_expression,
    resolve_cron_expression,
)
from embeds.PriceAlertEmbeds import PriceAlertEmbeds
from embeds.StocksEmbeds import StocksEmbeds
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility
from views.ScheduledJobActionView import ScheduledJobActionView
from views.StockActionView import StockActionView


class StocksCog(commands.Cog):
    stock_group = app_commands.Group(name="stock", description="Stock quotes")

    def __init__(self, client):
        self.client = client

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("StocksCog cog loaded")

    # Commands

    # Naredi embed...
    @stock_group.command(name="price", description="Get stock price")
    @app_commands.describe(
        ticker="Ticker symbol of the stock or ETF",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def fetch_stock(
        self,
        interaction: discord.Interaction,
        ticker: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await interaction.response.defer(thinking=True, ephemeral=ephemeral)
        await interaction.edit_original_response(
            content=f"• Fetching `{ticker.upper()}` ⏳", embed=None
        )

        response = await asyncio.to_thread(StocksEmbeds.stock_embed, ticker)

        action_view = None
        if response.get("embed") is not None:
            action_view = StockActionView(ticker)

        await interaction.edit_original_response(
            content=response.get("content"),
            embed=response.get("embed"),
            view=action_view,
        )

    @stock_group.command(name="schedule", description="Schedule recurring stock updates")
    @app_commands.describe(
        ticker="Ticker to include (for example: AAPL)",
        schedule="Cron expression or natural language schedule",
        header="Optional message shown above scheduled stock embeds",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def schedule_stock_updates(
        self,
        interaction: discord.Interaction,
        ticker: str,
        schedule: str,
        header: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        symbol = ticker.strip().upper()
        if not symbol:
            raise ValidationError(
                "Please provide a stock ticker.",
                ephemeral=ephemeral,
            )

        normalized_header = (header or "").strip()
        timezone = None
        if not is_valid_cron_expression(schedule):
            async def _continue_with_timezone(
                followup_interaction: discord.Interaction,
                resolved_timezone: str,
            ) -> None:
                await self._create_stock_schedule(
                    interaction=followup_interaction,
                    ticker=symbol,
                    schedule=schedule,
                    header=normalized_header,
                    ephemeral=ephemeral,
                    timezone=resolved_timezone,
                )

            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/stock schedule`.",
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._create_stock_schedule(
            interaction=interaction,
            ticker=symbol,
            schedule=schedule,
            header=normalized_header,
            ephemeral=ephemeral,
            timezone=timezone,
        )

    async def _create_stock_schedule(
        self,
        interaction: discord.Interaction,
        ticker: str,
        schedule: str,
        header: str,
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        try:
            cron_expression = await asyncio.to_thread(
                resolve_cron_expression,
                schedule,
                timezone=timezone,
            )
        except CronConversionError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

        payload = {"ticker": ticker}
        if header:
            payload["header"] = header

        manager = DailyJobManager()
        schedule_config = CronSchedule(expression=cron_expression)

        try:
            created_job = await asyncio.to_thread(
                manager.insert_job,
                interaction.guild_id,
                interaction.channel_id,
                "stock",
                payload,
                schedule_config,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while storing that stock job. Please try again.",
                ephemeral=ephemeral,
                cause=exc,
            )

        await interaction.followup.send(
            ephemeral=ephemeral,
            **DailyTaskEmbeds.job_details_embed(
                job_id=str(created_job.id),
                job_type="stock",
                channel_id=interaction.channel_id,
                schedule_text=schedule,
                cron_expression=cron_expression,
                payload=payload,
                ok=True,
            ),
            view=ScheduledJobActionView(
                job_id=str(created_job.id),
                channel_id=interaction.channel_id,
                guild_id=interaction.guild_id,
            ),
        )

    @stock_group.command(name="alert", description="Set a stock price alert")
    @app_commands.describe(
        ticker="Ticker symbol of the stock or ETF",
        target_price="Alert target price",
        condition="Alert when market price crosses above or below target",
        expires_in="Optional: how long this alert should stay active (for example: 3 days, tomorrow 9am)",
        destination="Where to send the alert (current channel, server channels, or DMs)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        condition=[
            app_commands.Choice(name="Crosses above target", value="above"),
            app_commands.Choice(name="Crosses below target", value="below"),
        ],
        visibility=VISIBILITY_CHOICES,
    )
    async def set_stock_alert(
        self,
        interaction: discord.Interaction,
        ticker: str,
        target_price: float,
        condition: app_commands.Choice[str],
        expires_in: Optional[str] = None,
        destination: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")
        symbol = ticker.strip().upper()
        if not symbol:
            raise ValidationError("Please provide a stock ticker.", ephemeral=ephemeral)
        if target_price <= 0:
            raise ValidationError(
                "Target price must be greater than 0.",
                ephemeral=ephemeral,
            )

        expires_text = (expires_in or "").strip()

        try:
            destination_type, destination_channel_id, destination_label = (
                normalize_alert_destination(interaction, destination)
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

        timezone = None
        if expires_text:
            async def _continue_with_timezone(
                followup_interaction: discord.Interaction,
                resolved_timezone: str,
            ) -> None:
                await self._set_stock_alert(
                    interaction=followup_interaction,
                    symbol=symbol,
                    target_price=target_price,
                    rule=condition.value,
                    expires_text=expires_text,
                    destination_type=destination_type,
                    destination_channel_id=destination_channel_id,
                    destination_label=destination_label,
                    ephemeral=ephemeral,
                    timezone=resolved_timezone,
                )

            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/stock alert`.",
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._set_stock_alert(
            interaction=interaction,
            symbol=symbol,
            target_price=target_price,
            rule=condition.value,
            expires_text=expires_text,
            destination_type=destination_type,
            destination_channel_id=destination_channel_id,
            destination_label=destination_label,
            ephemeral=ephemeral,
            timezone=timezone,
        )

    async def _set_stock_alert(
        self,
        interaction: discord.Interaction,
        symbol: str,
        target_price: float,
        rule: str,
        expires_text: str,
        destination_type: str,
        destination_channel_id: Optional[int],
        destination_label: str,
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        try:
            quote = await asyncio.to_thread(StocksFunctions.fetch_price, symbol)
        except Exception as exc:
            raise UserVisibleError(
                f"Failed to fetch `{symbol}` price data.",
                hint="Check the ticker and try again.",
                ephemeral=ephemeral,
                cause=exc,
            )

        currency_code = (quote.get("currency") or "").upper()
        if quote.get("price") is None:
            raise ValidationError(
                f"No live price data returned for `{symbol}`.",
                hint="Try another ticker or retry in a minute.",
                ephemeral=ephemeral,
            )

        expires_at = None
        if expires_text:
            api_key = env.get("OPENAI_API_KEY")
            if not api_key:
                raise ValidationError(
                    "OpenAI API key is not configured.",
                    hint="Set `OPENAI_API_KEY` to use natural-language alert expiry.",
                    ephemeral=ephemeral,
                )

            expires_at = await asyncio.to_thread(
                OpenAIFunctions.parse_alert_expiration_datetime,
                expires_text,
                api_key=api_key,
                timezone=timezone,
            )
            if expires_at is None:
                raise ValidationError(
                    "I couldn't understand that alert expiry value.",
                    hint="Try `3 days`, `tomorrow 8pm`, or `in 2 hours`.",
                    ephemeral=ephemeral,
                )

        alert_id = await asyncio.to_thread(
            create_alert,
            asset_type="stock",
            symbol=symbol,
            target_price=target_price,
            condition=rule,
            currency=(quote.get("currency") or "").lower() or None,
            guild_id=interaction.guild_id,
            channel_id=destination_channel_id,
            destination_type=destination_type,
            expires_at=expires_at,
            user_id=interaction.user.id,
        )

        target_price_label = (
            f"{target_price:,.2f}{f' {currency_code}' if currency_code else ''}"
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **PriceAlertEmbeds.alert_created_embed(
                alert_id=alert_id,
                asset_label="Stock",
                symbol_label=f"`{symbol}`",
                condition=rule,
                target_price_label=target_price_label,
                destination_label=destination_label,
                expires_at=expires_at,
            ),
        )

    @set_stock_alert.autocomplete("destination")
    async def stock_alert_destination_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = "",
    ) -> List[app_commands.Choice[str]]:
        return alert_destination_autocomplete(interaction, current)


async def setup(client):
    await client.add_cog(StocksCog(client))
