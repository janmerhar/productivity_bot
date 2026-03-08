import asyncio
from typing import Awaitable, Callable, Optional

import discord

from classes.UserSettingsFunctions import UserSettingsFunctions
from views.TimezoneModal import TimezoneModal


TimezoneResolvedHandler = Callable[[discord.Interaction, str], Awaitable[None]]


async def ensure_user_timezone(
    interaction: discord.Interaction,
    on_timezone_resolved: TimezoneResolvedHandler,
    continue_message: Optional[str] = None,
    response_ephemeral: bool = True,
) -> Optional[str]:
    timezone = await asyncio.to_thread(
        UserSettingsFunctions.get_timezone,
        interaction.user.id,
    )
    if timezone:
        return timezone

    await interaction.response.send_modal(
        TimezoneModal(
            user_id=interaction.user.id,
            on_timezone_resolved=on_timezone_resolved,
            continue_message=continue_message,
            response_ephemeral=response_ephemeral,
        )
    )
    return None
