from typing import Callable

import discord

from embeds.SettingsEmbeds import SettingsEmbeds


_CATEGORY_OPTIONS = [
    discord.SelectOption(
        label="Quick Start",
        value="quick_start",
        description="Setup steps and feature overview",
        emoji="🚀",
    ),
    discord.SelectOption(
        label="All Commands",
        value="reference",
        description="Every command at a glance",
        emoji="📖",
    ),
    discord.SelectOption(
        label="To-Do Lists",
        value="todo",
        description="Personal and shared task lists",
        emoji="📋",
    ),
    discord.SelectOption(
        label="Reminders",
        value="reminders",
        description="One-time and repeating reminders",
        emoji="⏰",
    ),
    discord.SelectOption(
        label="Habits",
        value="habits",
        description="Daily habit tracking and streaks",
        emoji="🔁",
    ),
    discord.SelectOption(
        label="Pomodoro Timer",
        value="pomodoro",
        description="Focus sessions with pause and extend",
        emoji="🍅",
    ),
    discord.SelectOption(
        label="Time Tracking",
        value="toggl",
        description="Toggl timers, projects, and tags",
        emoji="⏱",
    ),
]

_EMBED_FOR_CATEGORY: dict[str, Callable[[], discord.Embed]] = {
    "quick_start": SettingsEmbeds.help_welcome_embed,
    "reference": SettingsEmbeds.reference_embed,
    "todo": SettingsEmbeds.todo_embed,
    "reminders": SettingsEmbeds.reminders_embed,
    "habits": SettingsEmbeds.habits_embed,
    "pomodoro": SettingsEmbeds.pomodoro_embed,
    "toggl": SettingsEmbeds.toggl_embed,
}


class HelpView(discord.ui.View):
    def __init__(self, *, category: str = "quick_start") -> None:
        super().__init__(timeout=None)
        self._current_category = category
        self._rebuild()

    def _rebuild(self) -> None:
        from views.help_dynamic_items import HelpCategorySelect

        self.clear_items()
        self.add_item(HelpCategorySelect(self._current_category))
