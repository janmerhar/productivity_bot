import asyncio
import datetime
from typing import Any, Dict, Optional

import discord

from classes.OpenAIFunctions import OpenAIFunctions
from classes.PriceAlertFunctions import (
    fetch_user_alert_by_id,
    update_alert,
)
from classes.UserSettingsFunctions import UserSettingsFunctions
from config.env import settings
from services.discord_helpers import normalize_alert_destination
from services.error_reporting import ValidationError, handle_interaction_error


class StockAlertEditModal(discord.ui.Modal, title="Edit Stock Alert"):
    target_price = discord.ui.TextInput(
        label="Target price (optional)",
        placeholder="Leave empty to keep current value",
        required=False,
        max_length=32,
    )
    condition = discord.ui.TextInput(
        label="Condition (optional)",
        placeholder="above or below",
        required=False,
        max_length=16,
    )
    expires_in = discord.ui.TextInput(
        label="Expires in (optional)",
        placeholder="Leave empty to keep, use 'none' to clear",
        required=False,
        max_length=100,
    )
    destination = discord.ui.TextInput(
        label="Destination (optional)",
        placeholder="Leave empty to keep, or use dm/channel:<id>",
        required=False,
        max_length=100,
    )

    def __init__(
        self,
        parent_view: "StockAlertActionView",
        alert: Dict[str, Any],
    ) -> None:
        super().__init__()
        self._view = parent_view

        target_value = alert.get("target_price")
        if isinstance(target_value, (int, float)):
            self.target_price.default = f"{float(target_value):.2f}"

        condition_value = str(alert.get("condition") or "").strip().lower()
        if condition_value in {"above", "below"}:
            self.condition.default = condition_value

        destination_type = str(alert.get("destination_type") or "channel").strip().lower()
        channel_id = alert.get("channel_id")
        if destination_type == "dm":
            self.destination.default = "dm"
        elif channel_id:
            self.destination.default = f"channel:{channel_id}"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        target_text = str(self.target_price.value or "").strip()
        condition_text = str(self.condition.value or "").strip().lower()
        expires_text = str(self.expires_in.value or "").strip()
        destination_text = str(self.destination.value or "").strip()

        update_kwargs: Dict[str, Any] = {}

        if target_text:
            try:
                parsed_target = float(target_text)
            except ValueError as exc:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Target price must be a number.",
                        ephemeral=True,
                        cause=exc,
                    ),
                    ephemeral=True,
                )
                return
            if parsed_target <= 0:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Target price must be greater than 0.",
                        ephemeral=True,
                    ),
                    ephemeral=True,
                )
                return
            update_kwargs["target_price"] = parsed_target

        if condition_text:
            if condition_text not in {"above", "below"}:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        "Condition must be `above` or `below`.",
                        ephemeral=True,
                    ),
                    ephemeral=True,
                )
                return
            update_kwargs["condition"] = condition_text

        if destination_text:
            try:
                destination_type, channel_id, _ = normalize_alert_destination(
                    interaction,
                    destination_text,
                )
            except ValueError as exc:
                await handle_interaction_error(
                    interaction,
                    ValidationError(str(exc), ephemeral=True, cause=exc),
                    ephemeral=True,
                )
                return

            update_kwargs["destination_type"] = destination_type
            update_kwargs["channel_id"] = channel_id

        if expires_text:
            lowered = expires_text.lower()
            if lowered in {"none", "clear", "off"}:
                update_kwargs["clear_expires_at"] = True
            else:
                api_key = settings.openai_api_key
                if not api_key:
                    await handle_interaction_error(
                        interaction,
                        ValidationError(
                            "OpenAI API key is not configured.",
                            hint="Set `OPENAI_API_KEY` to parse natural-language expiry.",
                            ephemeral=True,
                        ),
                        ephemeral=True,
                    )
                    return

                timezone = await asyncio.to_thread(
                    UserSettingsFunctions.get_timezone,
                    interaction.user.id,
                )
                expires_at = await asyncio.to_thread(
                    OpenAIFunctions.parse_alert_expiration_datetime,
                    expires_text,
                    api_key=api_key,
                    timezone=timezone,
                )
                if expires_at is None:
                    await handle_interaction_error(
                        interaction,
                        ValidationError(
                            "I couldn't understand that expiry value.",
                            hint="Use values like `3 days`, `tomorrow 9am`, or `none`.",
                            ephemeral=True,
                        ),
                        ephemeral=True,
                    )
                    return
                update_kwargs["expires_at"] = expires_at

        if not update_kwargs:
            await interaction.followup.send(
                ephemeral=True,
                content="No changes to apply.",
            )
            return

        updated = await asyncio.to_thread(
            update_alert,
            self._view.alert_id,
            self._view.user_id,
            asset_type="stock",
            guild_id=self._view.guild_id,
            **update_kwargs,
        )
        if not updated:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That alert was not found or could not be updated.",
                    ephemeral=True,
                ),
                ephemeral=True,
            )
            return

        await self._view.refresh_state()
        await self._view.refresh_message()
        await interaction.followup.send(ephemeral=True, content="Alert updated.")


class StockAlertActionView(discord.ui.View):
    def __init__(
        self,
        *,
        alert_id: str,
        user_id: int,
        guild_id: Optional[int],
        timeout: float | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.alert_id = str(alert_id)
        self.user_id = user_id
        self.guild_id = guild_id
        self.alert: Optional[Dict[str, Any]] = None
        self.message: Optional[discord.Message] = None
        self._rebuild_items()

    @staticmethod
    def _target_label(value: Any, currency: str) -> str:
        try:
            parsed = float(value)
            base = f"{parsed:,.2f}"
        except (TypeError, ValueError):
            base = "unknown"
        return f"{base}{f' {currency}' if currency else ''}"

    @staticmethod
    def _expires_label(expires_at: Any) -> str:
        if isinstance(expires_at, datetime.datetime):
            return f"<t:{int(expires_at.timestamp())}:R>"
        return "No expiration"

    async def initialize(self) -> None:
        await self.refresh_state()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.user_id:
            return True
        await interaction.response.send_message(
            ephemeral=True,
            content="Only the user who opened this alert can manage it.",
        )
        return False

    async def refresh_state(self) -> None:
        self.alert = await asyncio.to_thread(
            fetch_user_alert_by_id,
            self.alert_id,
            self.user_id,
            "stock",
            self.guild_id,
            True,
        )
        self._rebuild_items()

    def _rebuild_items(self) -> None:
        from views.stock_alert_dynamic_items import (
            StockAlertDeleteButton,
            StockAlertEditButton,
            StockAlertToggleButton,
        )

        has_alert = self.alert is not None
        paused = bool((self.alert or {}).get("paused"))

        self.clear_items()
        self.add_item(
            StockAlertEditButton(
                self.alert_id,
                self.user_id,
                self.guild_id,
                disabled=not has_alert,
            )
        )
        self.add_item(
            StockAlertToggleButton(
                self.alert_id,
                self.user_id,
                self.guild_id,
                paused=paused,
                disabled=not has_alert,
            )
        )
        self.add_item(
            StockAlertDeleteButton(
                self.alert_id,
                self.user_id,
                self.guild_id,
                disabled=not has_alert,
            )
        )

    def payload(self) -> dict:
        embed = discord.Embed(
            title="Stock Alert Actions",
            color=discord.Colour.blurple(),
            timestamp=discord.utils.utcnow(),
        )

        if self.alert is None:
            embed.description = "This alert is no longer active."
            return {"embed": embed}

        symbol = str(self.alert.get("symbol") or "").strip().upper() or "UNKNOWN"
        condition = str(self.alert.get("condition") or "above").strip().lower()
        currency = str(self.alert.get("currency") or "").strip().upper()
        target = self._target_label(self.alert.get("target_price"), currency)
        destination_type = str(self.alert.get("destination_type") or "channel").lower()
        channel_id = self.alert.get("channel_id")
        destination = (
            "DM"
            if destination_type == "dm"
            else (f"<#{channel_id}>" if channel_id else "Channel")
        )
        status = "Paused" if bool(self.alert.get("paused")) else "Active"

        embed.add_field(name="Alert ID", value=f"`{self.alert_id}`", inline=False)
        embed.add_field(name="Symbol", value=f"`{symbol}`", inline=True)
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(
            name="Trigger",
            value=f"`{condition}` `{target}`",
            inline=False,
        )
        embed.add_field(name="Destination", value=destination, inline=True)
        embed.add_field(
            name="Expires",
            value=self._expires_label(self.alert.get("expires_at")),
            inline=True,
        )
        return {"embed": embed}

    async def refresh_message(self) -> None:
        if self.message is None:
            return
        try:
            await self.message.edit(view=self, **self.payload())
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
