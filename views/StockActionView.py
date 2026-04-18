import asyncio
from typing import Optional

import discord

from classes.DailyJob import CronSchedule
from classes.DailyJobManager import DailyJobManager
from classes.OpenAIFunctions import OpenAIFunctions
from classes.PriceAlertFunctions import create_alert
from classes.StocksFunctions import StocksFunctions
from config.env import settings
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.cron_schedule import (
    CronConversionError,
    is_valid_cron_expression,
    resolve_cron_expression,
)
from services.discord_helpers import normalize_alert_destination
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)
from services.timezone_gate import ensure_user_timezone
from views.ScheduledJobActionView import ScheduledJobActionView


class StockAlertModal(discord.ui.Modal, title="Create Stock Alert"):
    ticker = discord.ui.TextInput(
        label="Ticker",
        placeholder="e.g. AAPL",
        required=True,
        max_length=16,
    )
    target_price = discord.ui.TextInput(
        label="Target price",
        placeholder="e.g. 250",
        required=True,
        max_length=32,
    )
    condition = discord.ui.TextInput(
        label="Condition",
        placeholder="above or below",
        default="above",
        required=True,
        max_length=16,
    )
    expires_in = discord.ui.TextInput(
        label="Expires in (optional)",
        placeholder="e.g. 3 days, tomorrow 9am",
        required=False,
        max_length=100,
    )
    destination = discord.ui.TextInput(
        label="Destination (optional)",
        placeholder="dm or channel:<id>",
        required=False,
        max_length=100,
    )

    def __init__(self, symbol: str) -> None:
        super().__init__()
        self.ticker.default = symbol.strip().upper()

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
        timezone: Optional[str],
    ) -> None:
        try:
            quote = await asyncio.to_thread(StocksFunctions.fetch_price, symbol)
        except Exception as exc:
            raise UserVisibleError(
                f"Failed to fetch `{symbol}` price data.",
                hint="Check the ticker and try again.",
                ephemeral=False,
                cause=exc,
            ) from exc

        if quote.get("price") is None:
            raise ValidationError(
                f"No live price data returned for `{symbol}`.",
                hint="Try another ticker or retry in a minute.",
                ephemeral=False,
            )

        expires_at = None
        if expires_text:
            api_key = settings.openai_api_key
            if not api_key:
                raise ValidationError(
                    "OpenAI API key is not configured.",
                    hint="Set `OPENAI_API_KEY` to use natural-language alert expiry.",
                    ephemeral=False,
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
                    ephemeral=False,
                )

        currency_code = (quote.get("currency") or "").upper()
        alert_id = await asyncio.to_thread(
            create_alert,
            asset_type="stock",
            symbol=quote.get("symbol") or symbol,
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
        message = (
            f"Created stock alert `{alert_id}` for `{symbol}` when price is "
            f"`{rule}` `{target_price_label}`. Destination: {destination_label}."
        )
        if expires_at is not None:
            message = f"{message} Expires: <t:{int(expires_at.timestamp())}:f>."

        await interaction.followup.send(message, ephemeral=False)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        symbol = (self.ticker.value or "").strip().upper()
        destination_text = (self.destination.value or "").strip()
        expires_text = (self.expires_in.value or "").strip()

        try:
            target_price = float((self.target_price.value or "").strip())
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "Target price must be a number.",
                    ephemeral=False,
                    cause=exc,
                ),
            )
            return

        try:
            if not symbol:
                raise ValidationError("Please provide a stock ticker.", ephemeral=False)
            if target_price <= 0:
                raise ValidationError(
                    "Target price must be greater than 0.",
                    ephemeral=False,
                )

            rule = (self.condition.value or "").strip().lower()
            if rule not in {"above", "below"}:
                raise ValidationError(
                    "Condition must be either `above` or `below`.",
                    ephemeral=False,
                )

            destination_type, destination_channel_id, destination_label = (
                normalize_alert_destination(interaction, destination_text or None)
            )

            timezone = None
            if expires_text:

                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    try:
                        await self._set_stock_alert(
                            interaction=followup_interaction,
                            symbol=symbol,
                            target_price=target_price,
                            rule=rule,
                            expires_text=expires_text,
                            destination_type=destination_type,
                            destination_channel_id=destination_channel_id,
                            destination_label=destination_label,
                            timezone=resolved_timezone,
                        )
                    except Exception as exc:
                        await handle_interaction_error(
                            followup_interaction,
                            exc,
                            ephemeral=False,
                        )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing stock alert setup.",
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=False)
            await self._set_stock_alert(
                interaction=interaction,
                symbol=symbol,
                target_price=target_price,
                rule=rule,
                expires_text=expires_text,
                destination_type=destination_type,
                destination_channel_id=destination_channel_id,
                destination_label=destination_label,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=False)


class StockDailyJobModal(discord.ui.Modal, title="Schedule Daily Stock Check"):
    ticker = discord.ui.TextInput(
        label="Ticker",
        placeholder="e.g. AAPL",
        required=True,
        max_length=16,
    )
    schedule = discord.ui.TextInput(
        label="Schedule",
        placeholder="e.g. every day at 9am or 0 9 * * *",
        required=True,
        max_length=120,
    )
    header = discord.ui.TextInput(
        label="Message header (optional)",
        placeholder="e.g. Daily AAPL check",
        required=False,
        max_length=200,
    )

    def __init__(self, symbol: str) -> None:
        super().__init__()
        self.ticker.default = symbol.strip().upper()

    async def _create_stock_schedule(
        self,
        interaction: discord.Interaction,
        symbol: str,
        raw_schedule: str,
        header_text: str,
        timezone: Optional[str],
    ) -> None:
        try:
            cron_expression = await asyncio.to_thread(
                resolve_cron_expression,
                raw_schedule,
                timezone=timezone,
            )
        except CronConversionError as exc:
            raise ValidationError(str(exc), ephemeral=False, cause=exc) from exc
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while parsing that schedule.",
                ephemeral=False,
                cause=exc,
            ) from exc

        payload = {"ticker": symbol}
        if header_text:
            payload["header"] = header_text

        manager = DailyJobManager()
        try:
            created_job = await asyncio.to_thread(
                manager.insert_job,
                interaction.guild_id,
                interaction.channel_id,
                "stock",
                payload,
                CronSchedule(
                    expression=cron_expression,
                    timezone=timezone,
                ),
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while storing that job. Please try again.",
                ephemeral=False,
                cause=exc,
            ) from exc

        await interaction.followup.send(
            ephemeral=False,
            **DailyTaskEmbeds.job_details_embed(
                job_id=str(created_job.id),
                job_type="stock",
                channel_id=interaction.channel_id,
                schedule_text=raw_schedule,
                cron_expression=cron_expression,
                payload=payload,
                ok=True,
            ),
            view=ScheduledJobActionView(
                job_id=str(created_job.id),
                channel_id=interaction.channel_id,
                guild_id=interaction.guild_id,
                response_ephemeral=False,
            ),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        symbol = (self.ticker.value or "").strip().upper()
        raw_schedule = (self.schedule.value or "").strip()
        header_text = (self.header.value or "").strip()

        try:
            if not symbol:
                raise ValidationError("Please provide a stock ticker.", ephemeral=False)

            timezone = None
            if not is_valid_cron_expression(raw_schedule):

                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    try:
                        await self._create_stock_schedule(
                            interaction=followup_interaction,
                            symbol=symbol,
                            raw_schedule=raw_schedule,
                            header_text=header_text,
                            timezone=resolved_timezone,
                        )
                    except Exception as exc:
                        await handle_interaction_error(
                            followup_interaction,
                            exc,
                            ephemeral=False,
                        )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing stock schedule setup.",
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=False)
            await self._create_stock_schedule(
                interaction=interaction,
                symbol=symbol,
                raw_schedule=raw_schedule,
                header_text=header_text,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=False,
            )


class StockActionView(discord.ui.View):
    def __init__(self, symbol: str, *, timeout: float | None = None) -> None:
        super().__init__(timeout=timeout)
        self.symbol = symbol.strip().upper()
        self._build()

    def _build(self) -> None:
        self.clear_items()

        from views.stock_action_dynamic_items import (
            StockScheduleDailyCheckButton,
            StockSetAlertButton,
        )

        symbol = self.symbol
        self.add_item(
            StockSetAlertButton(
                symbol=symbol,
                disabled=not bool(symbol),
            )
        )
        self.add_item(
            StockScheduleDailyCheckButton(
                symbol=symbol,
                disabled=not bool(symbol),
            )
        )

    async def open_set_alert_modal(self, interaction: discord.Interaction) -> None:
        if not self.symbol:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "Missing stock ticker for this action.", ephemeral=False
                ),
            )
            return
        await interaction.response.send_modal(StockAlertModal(self.symbol))

    async def open_schedule_daily_check_modal(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.symbol:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "Missing stock ticker for this action.", ephemeral=False
                ),
            )
            return
        await interaction.response.send_modal(StockDailyJobModal(self.symbol))
