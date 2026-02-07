from typing import Optional

import discord
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
