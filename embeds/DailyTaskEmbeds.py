import json
from typing import Any, Dict, List, Mapping, Optional

import discord


class DailyTaskEmbeds:
    @staticmethod
    def _serialized_payload(payload: Optional[Mapping[str, Any]]) -> str:
        serialized = json.dumps(dict(payload or {}), ensure_ascii=True, sort_keys=True)
        if len(serialized) <= 900:
            return f"`{serialized}`"
        return f"`{serialized[:897]}...`"

    @staticmethod
    def reminder_embed(message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Reminder",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}

    @staticmethod
    def reminder_details_embed(
        reminder_id: str,
        channel_id: Optional[int],
        schedule_text: str,
        reminder: str,
        ping: Optional[str] = None,
        description: Optional[str] = None,
        thumbnail_url: Optional[str] = None,
        expires_after: Optional[str] = None,
        paused: bool = False,
        result_message: str = "Reminder updated.",
        ok: bool = True,
    ) -> dict:
        embed = discord.Embed(
            title="Reminder",
            description=result_message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        embed.add_field(name="ID", value=f"`{reminder_id}`", inline=True)
        embed.add_field(
            name="Channel",
            value=f"<#{channel_id}>" if channel_id else "unknown",
            inline=True,
        )
        embed.add_field(
            name="Status",
            value="paused" if paused else "active",
            inline=True,
        )
        embed.add_field(
            name="Schedule",
            value=f"`{schedule_text}`" if schedule_text else "unknown",
            inline=False,
        )
        embed.add_field(
            name="Name",
            value=(reminder or "Untitled reminder")[:1024],
            inline=False,
        )

        ping_value = str(ping or "").strip()
        if ping_value:
            embed.add_field(
                name="Ping",
                value=ping_value[:1024],
                inline=False,
            )

        description_value = str(description or "").strip()
        if description_value:
            embed.add_field(
                name="Description",
                value=description_value[:1024],
                inline=False,
            )

        thumbnail_value = str(thumbnail_url or "").strip()
        if thumbnail_value:
            embed.add_field(
                name="Thumbnail URL",
                value=thumbnail_value[:1024],
                inline=False,
            )

        expires_value = str(expires_after or "").strip()
        if expires_value:
            embed.add_field(
                name="Expires",
                value=f"`{expires_value}`",
                inline=False,
            )

        return {"embed": embed}

    @staticmethod
    def job_embed(message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Scheduled Job",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}

    @staticmethod
    def job_details_embed(
        job_id: str,
        job_type: str,
        channel_id: Optional[int],
        schedule_text: str,
        cron_expression: str,
        payload: Optional[Dict[str, Any]] = None,
        description: str = "Scheduled job created.",
        ok: bool = True,
    ) -> dict:
        embed = discord.Embed(
            title="Scheduled Job",
            description=description,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        embed.add_field(name="ID", value=f"`{job_id}`", inline=True)
        embed.add_field(name="Type", value=f"`{job_type}`", inline=True)
        embed.add_field(
            name="Channel",
            value=f"<#{channel_id}>" if channel_id else "unknown",
            inline=True,
        )
        embed.add_field(
            name="Schedule",
            value=f"`{schedule_text}`\nCron: `{cron_expression}`",
            inline=False,
        )
        if job_type == "stock":
            ticker_value = str((payload or {}).get("ticker") or "").strip().upper()
            if ticker_value:
                embed.add_field(name="Ticker", value=f"`{ticker_value}`", inline=True)
            header_value = str((payload or {}).get("header") or "").strip()
            if header_value:
                embed.add_field(name="Header", value=header_value[:1024], inline=False)
        else:
            embed.add_field(
                name="Payload",
                value=DailyTaskEmbeds._serialized_payload(payload),
                inline=False,
            )
        embed.add_field(name="Last Run", value="never", inline=False)
        return {"embed": embed}

    @staticmethod
    def jobs_list_embed(lines: List[str]) -> dict:
        embed = discord.Embed(
            title="Scheduled Jobs",
            color=discord.Colour.blurple(),
        )

        if not lines:
            embed.description = "No scheduled jobs found."
            return {"embed": embed}

        for index, line in enumerate(lines, start=1):
            label = line.lstrip("- ").strip()
            embed.add_field(name=f"Job {index}", value=label, inline=False)

        return {"embed": embed}

    @staticmethod
    def jobs_cancel_embed(message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Delete Job",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}
