from typing import Optional, Union

import discord
from discord import app_commands

VISIBILITY_DESC = "Who can see this response"
VISIBILITY_CHOICES = [
    app_commands.Choice(name="Private (only me)", value="private"),
    app_commands.Choice(name="Public (channel)", value="public"),
]


def resolve_visibility(
    visibility: Optional[Union[app_commands.Choice[str], str]],
    default: str,
) -> bool:
    value = visibility.value if isinstance(visibility, app_commands.Choice) else visibility
    if value is None:
        value = default
    return value == "private"


def resolve_visibility_for_context(
    guild_id: Optional[int],
    visibility: Optional[Union[app_commands.Choice[str], str]],
    *,
    guild_default: str,
    dm_default: str = "public",
) -> bool:
    default_visibility = guild_default if guild_id is not None else dm_default
    return resolve_visibility(visibility, default=default_visibility)


def visibility_value_from_ephemeral(ephemeral_default: bool) -> str:
    return "private" if ephemeral_default else "public"


def inherit_ephemeral_from_interaction(
    interaction: discord.Interaction,
    *,
    default: bool = False,
) -> bool:
    message = getattr(interaction, "message", None)
    if message is None:
        return default

    flags = getattr(message, "flags", None)
    if flags is None:
        return default

    return bool(flags.ephemeral)
