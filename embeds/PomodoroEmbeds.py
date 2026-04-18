# PomodoroEmbeds.py

import datetime
from typing import Optional, Union

import discord


class PomodoroEmbeds:
    @staticmethod
    def _round_half_up(value: float) -> int:
        return int(value + 0.5)

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
    def _format_static_remaining_time(remaining_seconds: Union[int, float]) -> str:
        total_seconds = max(0, int(remaining_seconds))
        if total_seconds < 60:
            return f"{total_seconds} second{'s' if total_seconds != 1 else ''}"
        if total_seconds < 3600:
            minutes = PomodoroEmbeds._round_half_up(total_seconds / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        if total_seconds < 86400:
            hours = PomodoroEmbeds._round_half_up(total_seconds / 3600)
            return f"{hours} hour{'s' if hours != 1 else ''}"

        days = PomodoroEmbeds._round_half_up(total_seconds / 86400)
        return f"{days} day{'s' if days != 1 else ''}"

    @staticmethod
    def paused_description(
        remaining_seconds: Optional[int] = None,
        remaining_minutes: Optional[Union[int, str]] = None,
    ) -> str:
        if remaining_seconds is not None:
            formatted = PomodoroEmbeds._format_static_remaining_time(remaining_seconds)
            return f"**Ends in {formatted}**"

        value = str(remaining_minutes).strip() if remaining_minutes is not None else ""
        if value.isdigit():
            minute_value = int(value)
            return (
                f"**Ends in {minute_value} minute{'s' if minute_value != 1 else ''} "
                "0 seconds**"
            )
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
            color=discord.Colour.red(),
        )
        embed.add_field(name=status_label, value=status_message, inline=False)
        embed.add_field(
            name=next_label,
            value=next_message,
            inline=False,
        )
        return {"embed": embed}
