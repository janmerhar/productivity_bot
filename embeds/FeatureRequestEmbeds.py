from typing import Any, Dict, Optional

import discord


class FeatureRequestEmbeds:
    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    @staticmethod
    def received_embed(document: Dict[str, Any]) -> dict:
        request_text = str(document.get("request") or "No details provided.")
        link = document.get("link")
        request_value = FeatureRequestEmbeds._truncate(request_text, 1024)

        embed = discord.Embed(
            title="Feature Request Received",
            description="Thanks! I've recorded your request.",
            color=discord.Colour.green(),
        )
        embed.add_field(name="Request", value=request_value, inline=False)

        if link:
            embed.add_field(
                name="Link",
                value=FeatureRequestEmbeds._truncate(str(link), 1024),
                inline=False,
            )

        attachment_url = document.get("attachment_url")
        if attachment_url:
            embed.add_field(
                name="Attachment",
                value=f"[View attachment]({attachment_url})",
                inline=False,
            )
            embed.set_image(url=str(attachment_url))

        request_id = document.get("_id")
        if request_id:
            embed.set_footer(text=f"Request id: {request_id}")

        return {"embed": embed}

