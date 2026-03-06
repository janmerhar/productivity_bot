import asyncio
import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser
import discord
from discord import app_commands
from discord.ext import commands

from classes.DailyJob import OneTimeSchedule2
from classes.DailyJobManager import DailyJobManager
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


def parse_time_string(
    raw: str,
    timezone: Optional[str] = None,
) -> Optional[datetime.datetime]:
    text = raw.strip()
    if not text:
        return None

    timezone_value = (timezone or "").strip()
    tzinfo = None
    if timezone_value:
        try:
            tzinfo = ZoneInfo(timezone_value)
        except ZoneInfoNotFoundError:
            tzinfo = None

    now = datetime.datetime.now(tzinfo) if tzinfo else datetime.datetime.now()
    settings = {
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": bool(tzinfo),
        "PREFER_DAY_OF_MONTH": "current",
    }
    if timezone_value:
        settings["TIMEZONE"] = timezone_value
        settings["RELATIVE_BASE"] = now

    dt = dateparser.parse(
        text,
        settings=settings,
    )

    if dt is not None:
        if tzinfo is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=tzinfo)
        dt = dt.replace(second=0, microsecond=0)
        if dt <= now:
            dt += datetime.timedelta(days=1)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt

    return None


class ReminderCog(commands.Cog):
    reminder_group = app_commands.Group(
        name="reminder",
        description="Manage reminders",
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("ReminderCog cog loaded")

    async def _send_not_implemented(
        self,
        interaction: discord.Interaction,
        command_name: str,
    ) -> None:
        await interaction.response.send_message(
            f"`{command_name}` is not implemented yet.",
            ephemeral=True,
        )

    @reminder_group.command(
        name="create",
        description="Create a one time reminder",
    )
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def reminder_create(
        self,
        interaction: discord.Interaction,
        time: str,
        message: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        ephemeral = resolve_visibility(visibility, default="private")

        async def _continue_with_timezone(
            followup_interaction: discord.Interaction,
            resolved_timezone: str,
        ) -> None:
            await self._create_reminder(
                interaction=followup_interaction,
                time=time,
                message=message,
                ephemeral=ephemeral,
                timezone=resolved_timezone,
            )

        timezone = await ensure_user_timezone(
            interaction,
            _continue_with_timezone,
            continue_message="Timezone saved as `{timezone}`. Continuing `/reminder create`.",
        )
        if timezone is None:
            return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._create_reminder(
            interaction=interaction,
            time=time,
            message=message,
            ephemeral=ephemeral,
            timezone=timezone,
        )

    @reminder_group.command(
        name="add",
        description="Create a one-time or recurring reminder.",
    )
    @app_commands.describe(
        reminder="Reminder title or primary content",
        time="Cron expression or natural language schedule",
        repeat="Repeat interval or custom repeat expression",
        ping="User or role to ping",
        thumbnail_url="Thumbnail URL",
        skip_days="Comma-separated days to skip",
        description="Reminder description",
        expires_after="Expiration time",
        destination_channel="Destination channel",
    )
    async def reminder_add(
        self,
        interaction: discord.Interaction,
        reminder: str,
        time: str,
        repeat: Optional[str] = None,
        ping: Optional[discord.Member | discord.Role] = None,
        thumbnail_url: Optional[str] = None,
        skip_days: Optional[str] = None,
        description: Optional[str] = None,
        expires_after: Optional[str] = None,
        destination_channel: Optional[discord.TextChannel] = None,
    ) -> None:
        await self._send_not_implemented(interaction, "/reminder add")

    @reminder_group.command(
        name="list",
        description="View active reminders for this server.",
    )
    @app_commands.describe(page="Page number")
    async def reminder_list(
        self,
        interaction: discord.Interaction,
        page: Optional[int] = None,
    ) -> None:
        await self._send_not_implemented(interaction, "/reminder list")

    @reminder_group.command(
        name="remove",
        description="Remove a scheduled reminder by ID.",
    )
    @app_commands.describe(reminder_id="Reminder ID")
    async def reminder_remove(
        self,
        interaction: discord.Interaction,
        reminder_id: str,
    ) -> None:
        await self._send_not_implemented(interaction, "/reminder remove")

    @reminder_group.command(
        name="edit",
        description="Edit an existing reminder.",
    )
    @app_commands.describe(reminder_id="Reminder ID")
    async def reminder_edit(
        self,
        interaction: discord.Interaction,
        reminder_id: str,
    ) -> None:
        await self._send_not_implemented(interaction, "/reminder edit")

    @reminder_group.command(
        name="pause",
        description="Pause reminders by ID or all at once.",
    )
    @app_commands.describe(reminder_id="Reminder ID")
    async def reminder_pause(
        self,
        interaction: discord.Interaction,
        reminder_id: str,
    ) -> None:
        await self._send_not_implemented(interaction, "/reminder pause")

    @reminder_group.command(
        name="resume",
        description="Resume paused reminders by ID or all at once.",
    )
    @app_commands.describe(
        reminder_id="Reminder ID",
        all="Resume all reminders",
    )
    async def reminder_resume(
        self,
        interaction: discord.Interaction,
        reminder_id: Optional[str] = None,
        all: Optional[bool] = None,
    ) -> None:
        await self._send_not_implemented(interaction, "/reminder resume")

    @reminder_group.command(
        name="customize",
        description="Set a custom reminder bot username and avatar.",
    )
    @app_commands.describe(
        username="Custom reminder bot username",
        avatar_url="Custom reminder bot avatar URL",
    )
    async def reminder_customize(
        self,
        interaction: discord.Interaction,
        username: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> None:
        await self._send_not_implemented(interaction, "/reminder customize")

    @reminder_group.command(
        name="dst-forward",
        description="Shift all reminders forward by one hour.",
    )
    async def reminder_dst_forward(self, interaction: discord.Interaction) -> None:
        await self._send_not_implemented(interaction, "/reminder dst-forward")

    @reminder_group.command(
        name="dst-backward",
        description="Shift all reminders backward by one hour.",
    )
    async def reminder_dst_backward(self, interaction: discord.Interaction) -> None:
        await self._send_not_implemented(interaction, "/reminder dst-backward")

    async def _create_reminder(
        self,
        interaction: discord.Interaction,
        time: str,
        message: str,
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        scheduled_dt = parse_time_string(time, timezone=timezone)
        if scheduled_dt is None:
            raise ValidationError(
                "I couldn't understand that time.",
                hint="Try '08:30', '8pm', or similar.",
                ephemeral=ephemeral,
            )

        job_schedule = OneTimeSchedule2(datetime=scheduled_dt.isoformat())
        payload = message.strip()
        job_type = "message"
        job_data = {"message": message}
        confirmation_time = scheduled_dt.strftime("%H:%M")
        confirmation = f"Got it! I'll post here at {confirmation_time}."

        if payload.lower().startswith("stock:"):
            stock_value = payload[6:].strip()
            stock_tokens = [
                token.strip().upper()
                for token in stock_value.replace(",", " ").split()
                if token.strip()
            ]
            if not stock_tokens:
                raise ValidationError(
                    "Please provide a stock ticker after `stock:`.",
                    ephemeral=ephemeral,
                )
            if len(stock_tokens) != 1:
                raise ValidationError(
                    "Please provide exactly one stock ticker after `stock:`.",
                    ephemeral=ephemeral,
                )

            job_type = "stock"
            symbol = stock_tokens[0]
            job_data = {"ticker": symbol}
            confirmation = (
                f"Got it! I'll post daily stock price for `{symbol}` at "
                f"{confirmation_time}."
            )

        manager = DailyJobManager()
        try:
            await asyncio.to_thread(
                manager.insert_job,
                interaction.guild_id,
                interaction.channel_id,
                job_type,
                job_data,
                job_schedule,
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while scheduling that task. Please try again.",
                ephemeral=ephemeral,
                cause=exc,
            )

        await interaction.followup.send(
            ephemeral=ephemeral,
            **DailyTaskEmbeds.reminder_embed(confirmation, ok=True),
        )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(ReminderCog(client))
