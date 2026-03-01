import datetime
from typing import Optional

import discord


class PriceAlertEmbeds:
    @staticmethod
    def _expires_label(expires_at: Optional[datetime.datetime]) -> str:
        if expires_at is None:
            return "No expiration"
        return f"<t:{int(expires_at.timestamp())}:f>"

    @staticmethod
    def alert_created_embed(
        alert_id: str,
        asset_label: str,
        symbol_label: str,
        condition: str,
        target_price_label: str,
        destination_label: str,
        expires_at: Optional[datetime.datetime] = None,
        description: Optional[str] = None,
    ) -> dict:
        embed = discord.Embed(
            title="Alert Created",
            description=description or f"{asset_label} alert is active.",
            color=discord.Colour.green(),
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(name="Alert ID", value=f"`{alert_id}`", inline=False)
        embed.add_field(name="Asset", value=symbol_label, inline=True)
        embed.add_field(
            name="Trigger",
            value=f"`{condition}` `{target_price_label}`",
            inline=True,
        )
        embed.add_field(name="Destination", value=destination_label, inline=False)
        embed.add_field(
            name="Expires",
            value=PriceAlertEmbeds._expires_label(expires_at),
            inline=False,
        )

        return {"embed": embed}
