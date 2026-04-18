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
        disabled: bool = False,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self.add_item(PomodoroRestartFocusButton(disabled=disabled))
        self.add_item(PomodoroRestartBreakButton(disabled=disabled))
