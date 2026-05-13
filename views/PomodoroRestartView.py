import datetime
from typing import Optional

import discord

from views.pomodoro_dynamic_items import (
    PomodoroRestartBreakButton,
    PomodoroRestartFocusButton,
)


class PomodoroRestartView(discord.ui.View):
    def __init__(
        self,
        *,
        user_id: int = 0,
        focus_duration: Optional[int] = None,
        break_duration: Optional[int] = None,
        streak: int = 0,
        chain_expires_at: Optional[datetime.datetime] = None,
        disabled: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.add_item(
            PomodoroRestartFocusButton(
                user_id=user_id,
                focus_duration=focus_duration,
                break_duration=break_duration,
                streak=streak,
                chain_expires_at=chain_expires_at,
                disabled=disabled,
            )
        )
        self.add_item(
            PomodoroRestartBreakButton(
                user_id=user_id,
                focus_duration=focus_duration,
                break_duration=break_duration,
                streak=streak,
                chain_expires_at=chain_expires_at,
                disabled=disabled,
            )
        )
