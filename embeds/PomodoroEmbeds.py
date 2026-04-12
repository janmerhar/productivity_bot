import datetime
import math
from typing import Optional, Union

import discord


class PomodoroEmbeds:
    @staticmethod
    def _round_half_up(value: float) -> int:
        return int(math.floor(value + 0.5))

    @staticmethod
    def _format_end_time(end_time: Optional[datetime.datetime]) -> str:
        if end_time is None:
            return "soon"
        return end_time.strftime("%H:%M")

    @staticmethod
    def _format_relative_end_time(end_time: Optional[datetime.datetime]) -> str:
        if end_time is None:
            return "soon"
        return f"<t:{int(end_time.timestamp())}:R>"

    @staticmethod
    def running_description(end_time: Optional[datetime.datetime]) -> str:
        return f"**Ends {PomodoroEmbeds._format_relative_end_time(end_time)}**"

    @staticmethod
    def _discord_relative_text_from_seconds(remaining_seconds: Union[int, float]) -> str:
        seconds = max(0, int(remaining_seconds))
        if seconds < 45:
            return "in a few seconds"
        if seconds < 90:
            return "in a minute"

        minutes = PomodoroEmbeds._round_half_up(seconds / 60)
        if minutes < 45:
            return f"in {minutes} minutes"
        if minutes < 90:
            return "in an hour"

        hours = PomodoroEmbeds._round_half_up(seconds / 3600)
        if hours < 22:
            return f"in {hours} hours"
        if hours < 36:
            return "in a day"

        days = PomodoroEmbeds._round_half_up(seconds / 86400)
        if days < 26:
            return f"in {days} days"
        if days < 46:
            return "in a month"

        months = PomodoroEmbeds._round_half_up(seconds / (86400 * 30.44))
        if days < 320:
            return f"in {max(2, months)} months"
        if days < 548:
            return "in a year"

        years = PomodoroEmbeds._round_half_up(seconds / (86400 * 365.25))
        return f"in {max(2, years)} years"

    @staticmethod
    def paused_description(
        remaining_seconds: Optional[int] = None,
        remaining_minutes: Optional[Union[int, str]] = None,
    ) -> str:
        if remaining_seconds is not None:
            return f"**Ends {PomodoroEmbeds._discord_relative_text_from_seconds(remaining_seconds)}**"

        value = str(remaining_minutes).strip() if remaining_minutes is not None else ""
        if value.isdigit():
            return f"**Ends in {value} minute{'s' if value != '1' else ''}**"
        return "**Ends soon**"

    @staticmethod
    def insert_timer_embed(
        mode: str,
        duration_minutes: Union[int, str],
        end_time: Optional[datetime.datetime],
        title: Optional[str] = None,
        description: Optional[str] = None,
        duration_label: str = "Duration",
        ends_label: str = "Ends",
    ) -> dict:
        resolved_title = title if title is not None else mode.capitalize()
        resolved_description = (
            description
            if description is not None
            else PomodoroEmbeds.running_description(end_time)
        )
        embed = discord.Embed(
            title=resolved_title,
            description=resolved_description,
            color=discord.Colour.green(),
        )
        embed.set_footer(text=f"{duration_minutes} min")

        return {"embed": embed}

    @staticmethod
    def timer_stopped_embed(
        status_message: str,
        *,
        title: str = "Pomodoro Stopped",
        description: str = "Your pomodoro timer has been stopped.",
        status_label: str = "Status",
        next_label: str = "Next",
        next_message: str = "Start a new focus or break timer using the buttons below.",
    ) -> dict:
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Colour.orange(),
        )
        embed.add_field(name=status_label, value=status_message, inline=False)
        embed.add_field(
            name=next_label,
            value=next_message,
            inline=False,
        )
        return {"embed": embed}
