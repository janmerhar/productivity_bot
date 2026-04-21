import re
from typing import Iterable, List, Mapping, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands

from services.visibility import resolve_visibility_for_context


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


async def resolve_reminder_destination(
    bot: commands.Bot,
    *,
    channel_id: Optional[int],
    data: Optional[Mapping[str, object]],
) -> Optional[discord.abc.Messageable]:
    destination_data = data or {}
    destination_type = str(
        destination_data.get("destination_type") or "channel"
    ).strip().lower()
    user_id_value = destination_data.get("user_id")
    user_id = user_id_value if isinstance(user_id_value, int) else None
    if destination_type == "private":
        return await resolve_alert_destination(
            bot,
            "dm",
            channel_id=None,
            user_id=user_id,
        )
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
    if cleaned in {"current", "current channel", "here"}:
        channel_id = interaction.channel_id
        if channel_id and interaction.guild is not None:
            return "channel", channel_id, f"<#{channel_id}>"
        return "dm", None, "your DMs"

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
    in_guild = interaction.guild is not None

    current_channel_id = interaction.channel_id
    if (
        in_guild
        and current_channel_id
        and (not query or "current" in query or "here" in query)
    ):
        choices.append(
            app_commands.Choice(
                name="Current channel",
                value="current",
            )
        )

    guild = interaction.guild
    if guild is not None:
        for channel in guild.text_channels:
            if len(choices) >= 24:
                break
            if current_channel_id and channel.id == current_channel_id:
                continue
            if (
                query
                and query not in channel.name.lower()
                and query not in str(channel.id)
            ):
                continue
            if not channel.permissions_for(interaction.user).view_channel:
                continue
            choices.append(
                app_commands.Choice(
                    name=f"#{channel.name}"[:100],
                    value=f"channel:{channel.id}",
                )
            )

    if not in_guild and (
        not query
        or "current" in query
        or "here" in query
        or "dm" in query
        or "direct" in query
        or "message" in query
        or "private" in query
    ):
        return [app_commands.Choice(name="Direct messages", value="dm")]

    if len(choices) < 25 and (
        not query
        or "dm" in query
        or "current" in query
        or "here" in query
        or "direct" in query
        or "message" in query
        or "private" in query
    ):
        choices.append(app_commands.Choice(name="Direct messages", value="dm"))

    return choices[:25]


def normalize_reminder_destination(
    interaction: discord.Interaction,
    destination: Optional[str],
) -> Tuple[str, Optional[int], str]:
    if not destination or not destination.strip():
        channel_id = interaction.channel_id
        if channel_id:
            return "channel", channel_id, f"<#{channel_id}>"
        return "private", None, "Private"

    cleaned = destination.strip().lower()
    if cleaned in {"current", "current channel", "here"}:
        channel_id = interaction.channel_id
        if channel_id and interaction.guild is not None:
            return "channel", channel_id, f"<#{channel_id}>"
        return "private", None, "Private"

    if cleaned in {"private", "dm", "direct messages", "your dms", "your dm"}:
        return "private", None, "Private"

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


def reminder_destination_autocomplete(
    interaction: discord.Interaction,
    current: str = "",
) -> List[app_commands.Choice[str]]:
    query = (current or "").strip().lower()
    choices: List[app_commands.Choice[str]] = []
    in_guild = interaction.guild is not None

    current_channel_id = interaction.channel_id
    if (
        in_guild
        and current_channel_id
        and (not query or "current" in query or "here" in query)
    ):
        choices.append(
            app_commands.Choice(
                name="Current channel",
                value="current",
            )
        )

    guild = interaction.guild
    if guild is not None:
        for channel in guild.text_channels:
            if len(choices) >= 24:
                break
            if current_channel_id and channel.id == current_channel_id:
                continue
            if (
                query
                and query not in channel.name.lower()
                and query not in str(channel.id)
            ):
                continue
            if not channel.permissions_for(interaction.user).view_channel:
                continue
            choices.append(
                app_commands.Choice(
                    name=f"#{channel.name}"[:100],
                    value=f"channel:{channel.id}",
                )
            )

    if not in_guild and (
        not query
        or "current" in query
        or "here" in query
        or "private" in query
        or "dm" in query
        or "direct" in query
        or "message" in query
    ):
        return [app_commands.Choice(name="Direct messages", value="private")]

    if len(choices) < 25 and (
        not query
        or "private" in query
        or "current" in query
        or "here" in query
        or "dm" in query
        or "direct" in query
        or "message" in query
    ):
        choices.append(app_commands.Choice(name="Private", value="private"))

    return choices[:25]


def normalize_habit_target(
    interaction: discord.Interaction,
    target: Optional[str],
) -> Tuple[str, Optional[int], str]:
    if not target or not target.strip():
        channel_id = interaction.channel_id
        if channel_id and interaction.guild is not None:
            return "channel", channel_id, f"<#{channel_id}>"
        return "personal", None, "Personal"

    cleaned = target.strip().lower()
    if cleaned in {"current", "current channel", "here", "this channel"}:
        channel_id = interaction.channel_id
        if channel_id and interaction.guild is not None:
            return "channel", channel_id, f"<#{channel_id}>"
        return "personal", None, "Personal"

    if cleaned in {"personal", "private", "dm", "direct messages", "your dms", "your dm"}:
        return "personal", None, "Personal"

    if not cleaned.startswith("channel:"):
        raise ValueError("Please choose a target from the autocomplete list.")

    channel_id_raw = cleaned.split(":", 1)[1].strip()
    try:
        channel_id = int(channel_id_raw)
    except ValueError as exc:
        raise ValueError("Target channel is invalid.") from exc

    guild = interaction.guild
    if guild is None:
        raise ValueError("Channel targets can only be selected inside a server.")

    channel = guild.get_channel(channel_id)
    if channel is None or not isinstance(channel, discord.TextChannel):
        raise ValueError("Please choose a text channel from this server.")
    if not channel.permissions_for(interaction.user).view_channel:
        raise ValueError("You do not have access to that channel.")

    return "channel", channel_id, f"<#{channel_id}>"


def habit_target_autocomplete(
    interaction: discord.Interaction,
    current: str = "",
) -> List[app_commands.Choice[str]]:
    query = (current or "").strip().lower()
    choices: List[app_commands.Choice[str]] = []

    guild = interaction.guild
    current_channel_id = interaction.channel_id
    if guild is not None and current_channel_id and (
        not query or "current" in query or "here" in query or "channel" in query
    ):
        choices.append(
            app_commands.Choice(
                name="This Channel",
                value="current",
            )
        )

    if guild is not None:
        for channel in guild.text_channels:
            if len(choices) >= 24:
                break
            if current_channel_id and channel.id == current_channel_id:
                continue
            if (
                query
                and query not in channel.name.lower()
                and query not in str(channel.id)
            ):
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
        or "personal" in query
        or "private" in query
        or "dm" in query
    ):
        choices.append(
            app_commands.Choice(
                name="Personal",
                value="personal",
            )
        )

    if guild is None:
        return [app_commands.Choice(name="Personal", value="personal")]

    return choices[:25]


def normalize_habit_list_scope(
    interaction: discord.Interaction,
    target: Optional[str],
) -> Tuple[str, Optional[int], str]:
    if interaction.guild is None:
        return "personal", None, "Personal"

    cleaned = str(target or "").strip().lower()
    if not cleaned:
        return "guild", None, "All Server Habits"

    if cleaned in {"guild", "server", "all server", "all guild", "all"}:
        return "guild", None, "All Server Habits"

    return normalize_habit_target(interaction, target)


def habit_list_scope_autocomplete(
    interaction: discord.Interaction,
    current: str = "",
) -> List[app_commands.Choice[str]]:
    if interaction.guild is None:
        return [app_commands.Choice(name="Personal", value="personal")]

    query = (current or "").strip().lower()
    choices: List[app_commands.Choice[str]] = []

    if (
        not query
        or "all" in query
        or "guild" in query
        or "server" in query
    ):
        choices.append(
            app_commands.Choice(
                name="All Server Habits",
                value="guild",
            )
        )

    current_channel_id = interaction.channel_id
    if current_channel_id and (
        not query or "current" in query or "here" in query or "channel" in query
    ):
        choices.append(
            app_commands.Choice(
                name="This Channel",
                value="current",
            )
        )

    for channel in interaction.guild.text_channels:
        if len(choices) >= 24:
            break
        if current_channel_id and channel.id == current_channel_id:
            continue
        if (
            query
            and query not in channel.name.lower()
            and query not in str(channel.id)
        ):
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
        or "personal" in query
        or "private" in query
        or "dm" in query
    ):
        choices.append(
            app_commands.Choice(
                name="Personal",
                value="personal",
            )
        )

    return choices[:25]


def format_reminder_mentions(
    guild: Optional[discord.Guild],
    raw_value: Optional[str],
) -> str:
    text = str(raw_value or "").strip()
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        token = match.group(0)
        raw_id = match.group(1) or match.group(2)
        if not raw_id.isdigit():
            return token
        entity_id = int(raw_id)

        if token.startswith("<@&"):
            if guild is None:
                return token
            role = guild.get_role(entity_id)
            return f"@{role.name}" if role is not None else token

        if guild is not None:
            member = guild.get_member(entity_id)
            if member is not None:
                return f"@{member.display_name}"

        return token

    formatted = re.sub(r"<@!?(\d+)>|<@&(\d+)>", lambda m: _replace(m), text)
    return formatted.replace("\n", ", ")


def resolve_scope_value(
    guild_id: Optional[int],
    scope: Optional[app_commands.Choice[str]],
    server_default: str = "channel",
    dm_default: str = "personal",
    allowed_values: Iterable[str] = ("channel", "personal"),
    dm_allowed_values: Optional[Iterable[str]] = None,
    dm_error_message: str = "That option is only available in servers.",
) -> str:
    scope_value = (
        scope.value if scope else (dm_default if guild_id is None else server_default)
    )
    allowed_set = set(allowed_values)
    if scope_value not in allowed_set:
        raise ValueError("Invalid scope.")

    dm_allowed_set = (
        set(dm_allowed_values) if dm_allowed_values is not None else {dm_default}
    )
    if guild_id is None and scope_value not in dm_allowed_set:
        raise ValueError(dm_error_message)

    return scope_value


def resolve_ephemeral_from_scope(
    guild_id: Optional[int],
    scope_value: str,
    visibility: Optional[app_commands.Choice[str]],
    private_scope_values: Iterable[str] = (),
    guild_default_visibility: str = "public",
    dm_default_visibility: str = "public",
) -> bool:
    private_scope_set = set(private_scope_values)
    guild_default_visibility = (
        "private" if scope_value in private_scope_set else guild_default_visibility
    )
    return resolve_visibility_for_context(
        guild_id,
        visibility,
        guild_default=guild_default_visibility,
        dm_default=dm_default_visibility,
    )


def resolve_todo_scope(
    guild_id: Optional[int],
    scope: Optional[app_commands.Choice[str]],
) -> str:
    return resolve_scope_value(
        guild_id=guild_id,
        scope=scope,
        server_default="channel",
        dm_default="personal",
        allowed_values=("channel", "personal"),
        dm_allowed_values=("personal",),
    )


def resolve_todo_ephemeral(
    guild_id: Optional[int],
    scope_value: str,
    visibility: Optional[app_commands.Choice[str]],
) -> bool:
    return resolve_ephemeral_from_scope(
        guild_id=guild_id,
        scope_value=scope_value,
        visibility=visibility,
        private_scope_values=("personal",),
        guild_default_visibility="public",
        dm_default_visibility="public",
    )


def resolve_habit_scope(
    guild_id: Optional[int],
    scope: Optional[app_commands.Choice[str]],
) -> str:
    return resolve_scope_value(
        guild_id=guild_id,
        scope=scope,
        server_default="channel",
        dm_default="personal",
        allowed_values=("channel", "personal"),
        dm_allowed_values=("personal",),
    )


def resolve_habit_ephemeral(
    guild_id: Optional[int],
    scope_value: str,
    visibility: Optional[app_commands.Choice[str]],
) -> bool:
    return resolve_ephemeral_from_scope(
        guild_id=guild_id,
        scope_value=scope_value,
        visibility=visibility,
        private_scope_values=("personal",),
        guild_default_visibility="public",
        dm_default_visibility="private",
    )
