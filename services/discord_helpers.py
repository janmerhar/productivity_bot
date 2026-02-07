from typing import List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands


async def resolve_messageable_channel(
    bot: commands.Bot,
    channel_id: Optional[int],
) -> Optional[discord.abc.Messageable]:
    if not channel_id:
        return None

    channel = bot.get_channel(channel_id)
    if channel is not None:
        return channel

    try:
        return await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def resolve_alert_destination(
    bot: commands.Bot,
    destination_type: str,
    channel_id: Optional[int],
    user_id: Optional[int],
) -> Optional[discord.abc.Messageable]:
    if destination_type == "dm":
        if not user_id:
            return None
        user = bot.get_user(user_id)
        if user is not None:
            return user
        try:
            return await bot.fetch_user(user_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None

    return await resolve_messageable_channel(bot, channel_id)


def normalize_alert_destination(
    interaction: discord.Interaction,
    destination: Optional[str],
) -> Tuple[str, Optional[int], str]:
    if not destination or not destination.strip():
        channel_id = interaction.channel_id
        if channel_id:
            return "channel", channel_id, f"<#{channel_id}>"
        return "dm", None, "your DMs"

    cleaned = destination.strip().lower()
    if cleaned == "dm":
        return "dm", None, "your DMs"

    if not cleaned.startswith("channel:"):
        raise ValueError("Please choose a destination from the autocomplete list.")

    channel_id_raw = cleaned.split(":", 1)[1].strip()
    try:
        channel_id = int(channel_id_raw)
    except ValueError as exc:
        raise ValueError("Destination channel is invalid.") from exc

    guild = interaction.guild
    if guild is None:
        raise ValueError("Channel destinations can only be selected inside a server.")

    channel = guild.get_channel(channel_id)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise ValueError("Please choose a text channel from this server.")

    return "channel", channel_id, f"<#{channel_id}>"


def alert_destination_autocomplete(
    interaction: discord.Interaction,
    current: str = "",
) -> List[app_commands.Choice[str]]:
    query = (current or "").strip().lower()
    choices: List[app_commands.Choice[str]] = []

    current_channel_id = interaction.channel_id
    current_channel_name = getattr(interaction.channel, "name", None)
    if current_channel_id and (not query or "current" in query or "here" in query):
        label = (
            f"Current channel (#{current_channel_name})"
            if current_channel_name
            else "Current channel"
        )
        choices.append(
            app_commands.Choice(
                name=label[:100],
                value=f"channel:{current_channel_id}",
            )
        )

    guild = interaction.guild
    if guild is not None:
        for channel in guild.text_channels:
            if len(choices) >= 24:
                break
            if current_channel_id and channel.id == current_channel_id:
                continue
            if query and query not in channel.name.lower() and query not in str(channel.id):
                continue
            if not channel.permissions_for(interaction.user).view_channel:
                continue
            choices.append(
                app_commands.Choice(
                    name=f"#{channel.name}"[:100],
                    value=f"channel:{channel.id}",
                )
            )

    if len(choices) < 25 and (
        not query
        or "dm" in query
        or "direct" in query
        or "message" in query
        or "private" in query
    ):
        choices.append(app_commands.Choice(name="Direct messages", value="dm"))

    return choices[:25]
