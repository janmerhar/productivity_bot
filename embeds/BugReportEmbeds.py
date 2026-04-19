from typing import Any, Dict

import discord


class BugReportEmbeds:
    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return f"{text[: limit - 3]}..."

    @staticmethod
    def received_embed(document: Dict[str, Any]) -> dict:
        bug_text = str(document.get("description") or "No details provided.")
        link = document.get("link")
        bug_value = BugReportEmbeds._truncate(bug_text, 1024)

        embed = discord.Embed(
            title="Bug Report Received",
            description="Thanks! I've recorded the issue.",
            color=discord.Colour.orange(),
        )
        embed.add_field(name="Bug", value=bug_value, inline=False)

        if link:
            embed.add_field(
                name="Link",
                value=BugReportEmbeds._truncate(str(link), 1024),
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

        report_id = document.get("_id")
        if report_id:
            embed.set_footer(text=f"Report id: {report_id}")

        return {"embed": embed}
