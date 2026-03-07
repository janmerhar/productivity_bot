from typing import Optional

import discord

from classes.DailyJob import DailyJob
from classes.ReminderFunctions import ReminderFunctions
from services.discord_helpers import format_reminder_mentions


class ReminderOutputView(discord.ui.View):
    def __init__(
        self,
        *,
        job: DailyJob,
        guild: Optional[discord.Guild],
        result_message: str,
        ok: bool = True,
        timeout: float = 3600,
    ) -> None:
        super().__init__(timeout=timeout)
        self.job = job
        self.guild = guild
        self.result_message = result_message
        self.ok = bool(ok)
        self.job_id = str(job.id)
        self.guild_id = job.guild_id
        self.channel_id = job.channel_id

    def _embed(self) -> discord.Embed:
        values = ReminderFunctions.reminder_edit_values(self.job)
        ping_value = format_reminder_mentions(
            self.guild,
            values.get("ping_text"),
        )
        description_value = str(values.get("description") or "").strip()
        thumbnail_value = str(values.get("thumbnail_url") or "").strip()
        expires_value = str(values.get("expires_after") or "").strip()

        embed = discord.Embed(
            title="Reminder",
            description=self.result_message,
            color=discord.Colour.green() if self.ok else discord.Colour.red(),
        )
        embed.add_field(name="ID", value=f"`{self.job_id}`", inline=True)
        embed.add_field(
            name="Channel",
            value=f"<#{self.channel_id}>" if self.channel_id else "unknown",
            inline=True,
        )
        embed.add_field(
            name="Status",
            value="paused" if ReminderFunctions.is_paused(self.job) else "active",
            inline=True,
        )
        embed.add_field(
            name="Schedule",
            value=f"`{values.get('schedule')}`" if values.get("schedule") else "unknown",
            inline=False,
        )
        embed.add_field(
            name="Name",
            value=(values.get("reminder") or "Untitled reminder")[:1024],
            inline=False,
        )

        if ping_value:
            embed.add_field(name="Ping", value=ping_value[:1024], inline=False)

        if description_value:
            embed.add_field(
                name="Description",
                value=description_value[:1024],
                inline=False,
            )

        if thumbnail_value:
            embed.add_field(
                name="Thumbnail URL",
                value=thumbnail_value[:1024],
                inline=False,
            )

        if expires_value:
            embed.add_field(
                name="Expires",
                value=f"`{expires_value}`",
                inline=False,
            )

        return embed

    def payload(self) -> dict:
        return {"embed": self._embed()}

    def response_payload(self) -> dict:
        payload = self.payload()
        if self.children:
            payload["view"] = self
        return payload
