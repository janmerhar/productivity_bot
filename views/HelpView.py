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


class _CategorySelect(discord.ui.Select):
    def __init__(self, current_value: str) -> None:
        options = [
            discord.SelectOption(
                label=opt.label,
                value=opt.value,
                description=opt.description,
                emoji=opt.emoji,
                default=opt.value == current_value,
            )
            for opt in _CATEGORY_OPTIONS
        ]
        super().__init__(
            placeholder="Browse a category...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view: HelpView = self.view  # type: ignore[assignment]
        selected = self.values[0]
        builder = _EMBED_FOR_CATEGORY.get(selected, SettingsEmbeds.help_welcome_embed)
        view._current_category = selected
        view._rebuild()
        await interaction.response.edit_message(embed=builder(), view=view)


class HelpView(discord.ui.View):
    def __init__(self, *, category: str = "quick_start") -> None:
        super().__init__(timeout=None)
        self._current_category = category
        self._rebuild()

    def _rebuild(self) -> None:
        self.clear_items()
        self.add_item(_CategorySelect(self._current_category))
