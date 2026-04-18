import asyncio
from typing import Optional

import discord

from classes.CryptoFunctions import CryptoFunctions
from classes.DailyJob import CronSchedule
from classes.DailyJobManager import DailyJobManager
from classes.OpenAIFunctions import OpenAIFunctions
from classes.PriceAlertFunctions import create_alert
from config.env import env
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


class CryptoAlertModal(discord.ui.Modal, title="Create Crypto Alert"):
    currency = discord.ui.TextInput(
        label="Currency",
        placeholder="e.g. usd",
        required=True,
        max_length=16,
    )
    target_price = discord.ui.TextInput(
        label="Target price",
        placeholder="e.g. 95000",
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

    def __init__(self, coin_id: str, currency: str) -> None:
        super().__init__()
        self.coin_id = coin_id.strip().lower()
        self.currency.default = currency.strip().lower() or "usd"

    async def _set_crypto_alert(
        self,
        interaction: discord.Interaction,
        coin_id: str,
        vs_currency: str,
        target_price: float,
        rule: str,
        expires_text: str,
        destination_type: str,
        destination_channel_id: Optional[int],
        destination_label: str,
        timezone: Optional[str],
    ) -> None:
        try:
            results = await asyncio.to_thread(
                CryptoFunctions.fetch_prices,
                [coin_id],
                vs_currency,
                ("24h", "7d", "30d"),
            )
        except Exception as exc:
            raise UserVisibleError(
                f"Failed to fetch `{coin_id}` price data.",
                hint="Check the coin id and currency.",
                ephemeral=True,
                cause=exc,
            ) from exc

        if not results:
            raise ValidationError(
                f"No market data returned for `{coin_id}` in `{vs_currency}`.",
                hint="Use CoinGecko ids such as `bitcoin` or `ethereum`.",
                ephemeral=True,
            )

        coin = results[0]
        if coin.get("current_price") is None:
            raise ValidationError(
                f"No live price data returned for `{coin_id}`.",
                ephemeral=True,
            )

        expires_at = None
        if expires_text:
            api_key = env.get("OPENAI_API_KEY")
            if not api_key:
                raise ValidationError(
                    "OpenAI API key is not configured.",
                    hint="Set `OPENAI_API_KEY` to use natural-language alert expiry.",
                    ephemeral=True,
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
                    ephemeral=True,
                )

        alert_id = await asyncio.to_thread(
            create_alert,
            asset_type="crypto",
            symbol=coin.get("id") or coin_id,
            target_price=target_price,
            condition=rule,
            currency=vs_currency,
            guild_id=interaction.guild_id,
            channel_id=destination_channel_id,
            destination_type=destination_type,
            expires_at=expires_at,
            user_id=interaction.user.id,
        )

        coin_name = coin.get("name") or coin_id
        message = (
            f"Created crypto alert `{alert_id}` for `{coin_name}` "
            f"when price is `{rule}` "
            f"`{target_price:,.6f} {vs_currency.upper()}`. "
            f"Destination: {destination_label}."
        )
        if expires_at is not None:
            message = f"{message} Expires: <t:{int(expires_at.timestamp())}:f>."

        await interaction.followup.send(message, ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        coin_id = self.coin_id
        vs_currency = (self.currency.value or "").strip().lower()
        destination_text = (self.destination.value or "").strip()
        expires_text = (self.expires_in.value or "").strip()

        try:
            target_price = float((self.target_price.value or "").strip())
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "Target price must be a number.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        try:
            destination_type, destination_channel_id, destination_label = (
                normalize_alert_destination(interaction, destination_text or None)
            )
            if not vs_currency:
                raise ValidationError("Please provide a currency.", ephemeral=True)
            if target_price <= 0:
                raise ValidationError(
                    "Target price must be greater than 0.",
                    ephemeral=True,
                )

            rule = (self.condition.value or "").strip().lower()
            if rule not in {"above", "below"}:
                raise ValidationError(
                    "Condition must be either `above` or `below`.",
                    ephemeral=True,
                )

            timezone = None
            if expires_text:

                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    try:
                        await self._set_crypto_alert(
                            interaction=followup_interaction,
                            coin_id=coin_id,
                            vs_currency=vs_currency,
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
                            ephemeral=True,
                        )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing crypto alert setup.",
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=True)
            await self._set_crypto_alert(
                interaction=interaction,
                coin_id=coin_id,
                vs_currency=vs_currency,
                target_price=target_price,
                rule=rule,
                expires_text=expires_text,
                destination_type=destination_type,
                destination_channel_id=destination_channel_id,
                destination_label=destination_label,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)


class CryptoDailyJobModal(discord.ui.Modal, title="Schedule Daily Crypto Check"):
    ticker = discord.ui.TextInput(
        label="Ticker (CoinGecko id)",
        placeholder="e.g. bitcoin",
        required=True,
        max_length=64,
    )
    currency = discord.ui.TextInput(
        label="Currency",
        placeholder="e.g. usd",
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
        placeholder="e.g. Daily BTC check",
        required=False,
        max_length=200,
    )

    def __init__(self, coin_id: str, currency: str) -> None:
        super().__init__()
        self.ticker.default = coin_id.strip().lower()
        self.currency.default = currency.strip().lower() or "usd"

    async def _create_crypto_schedule(
        self,
        interaction: discord.Interaction,
        coin_id: str,
        currency: str,
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
            raise ValidationError(str(exc), ephemeral=True, cause=exc) from exc
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while parsing that schedule.",
                ephemeral=True,
                cause=exc,
            ) from exc

        payload = {"tickers": [coin_id], "currency": currency}
        if header_text:
            payload["header"] = header_text

        manager = DailyJobManager()
        try:
            await asyncio.to_thread(
                manager.insert_job,
                interaction.guild_id,
                interaction.channel_id,
                "crypto",
                payload,
                CronSchedule(
                    expression=cron_expression,
                    timezone=timezone,
                ),
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while storing that job. Please try again.",
                ephemeral=True,
                cause=exc,
            ) from exc

        await interaction.followup.send(
            ephemeral=True,
            **DailyTaskEmbeds.job_embed(
                (
                    f"Scheduled `crypto` job for `{coin_id}` on `{raw_schedule}`. "
                    f"(Cron: `{cron_expression}`)"
                ),
                ok=True,
            ),
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        coin_id = (self.ticker.value or "").strip().lower()
        currency = (self.currency.value or "").strip().lower()
        raw_schedule = (self.schedule.value or "").strip()
        header_text = (self.header.value or "").strip()

        try:
            if not coin_id:
                raise ValidationError("Please provide a crypto ticker.", ephemeral=True)
            if not currency:
                raise ValidationError("Please provide a currency.", ephemeral=True)

            timezone = None
            if not is_valid_cron_expression(raw_schedule):

                async def _continue_with_timezone(
                    followup_interaction: discord.Interaction,
                    resolved_timezone: str,
                ) -> None:
                    try:
                        await self._create_crypto_schedule(
                            interaction=followup_interaction,
                            coin_id=coin_id,
                            currency=currency,
                            raw_schedule=raw_schedule,
                            header_text=header_text,
                            timezone=resolved_timezone,
                        )
                    except Exception as exc:
                        await handle_interaction_error(
                            followup_interaction,
                            exc,
                            ephemeral=True,
                        )

                timezone = await ensure_user_timezone(
                    interaction,
                    _continue_with_timezone,
                    continue_message="Timezone saved as `{timezone}`. Continuing crypto schedule setup.",
                )
                if timezone is None:
                    return

            await interaction.response.defer(ephemeral=True)
            await self._create_crypto_schedule(
                interaction=interaction,
                coin_id=coin_id,
                currency=currency,
                raw_schedule=raw_schedule,
                header_text=header_text,
                timezone=timezone,
            )
        except Exception as exc:
            await handle_interaction_error(interaction, exc, ephemeral=True)


class CryptoActionView(discord.ui.View):
    def __init__(
        self,
        coin_id: str,
        currency: str,
        *,
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.coin_id = coin_id.strip().lower()
        self.currency = currency.strip().lower() or "usd"
        self._build()

    def _build(self) -> None:
        self.clear_items()

        from views.crypto_action_dynamic_items import (
            CryptoScheduleDailyCheckButton,
            CryptoSetAlertButton,
        )

        has_coin = bool(self.coin_id)
        self.add_item(
            CryptoSetAlertButton(
                coin_id=self.coin_id,
                currency=self.currency,
                disabled=not has_coin,
            )
        )
        self.add_item(
            CryptoScheduleDailyCheckButton(
                coin_id=self.coin_id,
                currency=self.currency,
                disabled=not has_coin,
            )
        )

    async def open_set_alert_modal(self, interaction: discord.Interaction) -> None:
        if not self.coin_id:
            await handle_interaction_error(
                interaction,
                ValidationError("Missing coin id for this action.", ephemeral=True),
            )
            return
        await interaction.response.send_modal(
            CryptoAlertModal(
                coin_id=self.coin_id,
                currency=self.currency,
            )
        )

    async def open_schedule_daily_check_modal(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if not self.coin_id:
            await handle_interaction_error(
                interaction,
                ValidationError("Missing coin id for this action.", ephemeral=True),
            )
            return
        await interaction.response.send_modal(
            CryptoDailyJobModal(
                coin_id=self.coin_id,
                currency=self.currency,
            )
        )
