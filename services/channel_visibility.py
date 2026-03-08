from typing import Callable, Iterable, Optional, TypeVar

import discord

T = TypeVar("T")


def can_view_channel(
    interaction: discord.Interaction,
    channel_id: Optional[int],
) -> bool:
    if channel_id is None:
        return False

    if interaction.guild is None:
        return channel_id == interaction.channel_id

    channel = interaction.guild.get_channel_or_thread(channel_id)
    if channel is None:
        return False

    return channel.permissions_for(interaction.user).view_channel


def filter_visible_items(
    interaction: discord.Interaction,
    items: Iterable[T],
    *,
    channel_id_getter: Callable[[T], Optional[int]],
) -> list[T]:
    return [
        item
        for item in items
        if can_view_channel(interaction, channel_id_getter(item))
    ]
