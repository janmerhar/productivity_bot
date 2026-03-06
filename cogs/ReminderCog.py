import asyncio
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from classes.ReminderFunctions import ReminderFunctions
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility


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
        ephemeral = True

        needs_timezone = ReminderFunctions.needs_timezone(
            time,
            repeat=repeat,
            expires_after=expires_after,
        )

        async def _continue_with_timezone(
            followup_interaction: discord.Interaction,
            resolved_timezone: str,
        ) -> None:
            await self._create_reminder_from_options(
                interaction=followup_interaction,
                reminder=reminder,
                time=time,
                repeat=repeat,
                ping=ping,
                thumbnail_url=thumbnail_url,
                skip_days=skip_days,
                description=description,
                expires_after=expires_after,
                destination_channel=destination_channel,
                ephemeral=ephemeral,
                timezone=resolved_timezone,
            )

        timezone = None
        if needs_timezone:
            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/reminder add`.",
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._create_reminder_from_options(
            interaction=interaction,
            reminder=reminder,
            time=time,
            repeat=repeat,
            ping=ping,
            thumbnail_url=thumbnail_url,
            skip_days=skip_days,
            description=description,
            expires_after=expires_after,
            destination_channel=destination_channel,
            ephemeral=ephemeral,
            timezone=timezone,
        )

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
        created_job, confirmation = await asyncio.to_thread(
            ReminderFunctions.create_reminder,
            interaction.guild_id,
            interaction.channel_id,
            message,
            time,
            ephemeral=ephemeral,
            timezone=timezone,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **DailyTaskEmbeds.reminder_embed(
                f"{confirmation}\nReminder ID: `{created_job.id}`",
                ok=True,
            ),
        )

    async def _create_reminder_from_options(
        self,
        interaction: discord.Interaction,
        reminder: str,
        time: str,
        repeat: Optional[str],
        ping: Optional[discord.Member | discord.Role],
        thumbnail_url: Optional[str],
        skip_days: Optional[str],
        description: Optional[str],
        expires_after: Optional[str],
        destination_channel: Optional[discord.TextChannel],
        ephemeral: bool,
        timezone: Optional[str],
    ) -> None:
        ping_text = ping.mention if ping is not None else None
        destination_channel_id = (
            destination_channel.id if destination_channel is not None else None
        )
        created_job, confirmation = await asyncio.to_thread(
            ReminderFunctions.create_reminder,
            interaction.guild_id,
            interaction.channel_id,
            reminder,
            time,
            repeat,
            ping_text,
            thumbnail_url,
            skip_days,
            description,
            expires_after,
            destination_channel_id,
            ephemeral,
            timezone,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **DailyTaskEmbeds.reminder_embed(
                f"{confirmation}\nReminder ID: `{created_job.id}`",
                ok=True,
            ),
        )


async def setup(client: commands.Bot) -> None:
    await client.add_cog(ReminderCog(client))
