import asyncio
from typing import Awaitable, Callable, Optional

import discord

from classes.TogglCredentials import TogglCredentials
from views.TogglApiKeyModal import TogglApiKeyModal


ApiKeyResolvedHandler = Callable[[discord.Interaction, str], Awaitable[None]]


async def ensure_toggl_api_key(
    interaction: discord.Interaction,
    on_api_key_resolved: ApiKeyResolvedHandler,
    continue_message: Optional[str] = None,
) -> Optional[str]:
    guild_id = interaction.guild_id
    if guild_id is None:
        return None

    api_key = await asyncio.to_thread(
        TogglCredentials.get_key,
        guild_id,
        interaction.user.id,
    )
    if api_key:
        return api_key

    await interaction.response.send_modal(
        TogglApiKeyModal(
            user_id=interaction.user.id,
            guild_id=guild_id,
            on_api_key_resolved=on_api_key_resolved,
            continue_message=continue_message,
        )
    )
    return None
