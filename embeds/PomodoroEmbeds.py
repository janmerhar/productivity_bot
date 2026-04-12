import datetime
from typing import Optional, Union

import discord


class PomodoroEmbeds:
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
        seconds = max(0, int(remaining_seconds))
        if seconds < 60:
            return "less than a minute"

        total_minutes = seconds // 60
        days, remaining_minutes = divmod(total_minutes, 1440)
        hours, minutes = divmod(remaining_minutes, 60)

        parts = []
        if days > 0:
            parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0:
            parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0:
            parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

        if not parts:
            return "1 minute"

        return " ".join(parts[:2])

    @staticmethod
    def paused_description(
        remaining_seconds: Optional[int] = None,
        remaining_minutes: Optional[Union[int, str]] = None,
    ) -> str:
        if remaining_seconds is not None:
            formatted = PomodoroEmbeds._format_static_remaining_time(remaining_seconds)
            return f"**Paused with {formatted} remaining**"

        value = str(remaining_minutes).strip() if remaining_minutes is not None else ""
        if value.isdigit():
            return f"**Paused with {value} minute{'s' if value != '1' else ''} remaining**"
        return "**Paused**"

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
