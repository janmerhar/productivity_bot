import asyncio
from typing import Awaitable, Callable, Optional

import discord

from classes.UserSettingsFunctions import UserSettingsFunctions
from views.TogglApiKeyModal import TogglApiKeyModal


ApiKeyResolvedHandler = Callable[[discord.Interaction, str], Awaitable[None]]


async def ensure_toggl_api_key(
    interaction: discord.Interaction,
    on_api_key_resolved: ApiKeyResolvedHandler,
    continue_message: Optional[str] = None,
) -> Optional[str]:
    api_key = await asyncio.to_thread(
        UserSettingsFunctions.get_toggl_api_key,
        interaction.user.id,
    )
    if api_key:
        return api_key

    await interaction.response.send_modal(
        TogglApiKeyModal(
            user_id=interaction.user.id,
            on_api_key_resolved=on_api_key_resolved,
            continue_message=continue_message,
        )
    )
    return None
