import re
from typing import List, Optional, Tuple

import discord

from services.error_reporting import ValidationError


def destination_option_value(channel_id: int) -> str:
    return f"channel:{channel_id}"


def parse_reminder_destination_value(value: str) -> Tuple[str, Optional[int]]:
    cleaned = value.strip()
    if cleaned.lower() in {"private", "dm", "direct messages", "your dms"}:
        return "private", None

    mention_match = re.fullmatch(r"<#(\d+)>", cleaned)
    if mention_match is not None:
        return "channel", int(mention_match.group(1))

    if cleaned.lower().startswith("channel:"):
        try:
            return "channel", int(cleaned.split(":", 1)[1].strip())
        except ValueError as exc:
            raise ValidationError("Please provide a valid destination channel.") from exc

    if cleaned.isdigit():
        return "channel", int(cleaned)

    raise ValidationError("Please provide `Private`, a channel mention, or a channel id.")


def build_reminder_destination_select_options(
    guild: Optional[discord.Guild],
    current_channel_id: Optional[int],
    *,
    is_private_selected: bool = False,
) -> List[discord.SelectOption]:
    options: List[discord.SelectOption] = [
        discord.SelectOption(
            label="Private",
            value="private",
            default=is_private_selected,
        )
    ]

    if guild is None:
        return options

    for channel in guild.text_channels:
        options.append(
            discord.SelectOption(
                label=f"#{channel.name}"[:100],
                value=destination_option_value(channel.id),
                default=(
                    not is_private_selected
                    and current_channel_id is not None
                    and channel.id == current_channel_id
                ),
            )
        )
        if len(options) >= 25:
            break

    return options
