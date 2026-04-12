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
    def insert_timer_embed(
        mode: str,
        duration_minutes: Union[int, str],
        end_time: Optional[datetime.datetime],
        title: Optional[str] = None,
        description: Optional[str] = None,
        duration_label: str = "Duration",
        ends_label: str = "Ends",
    ) -> dict:
        resolved_title = (
            title
            if title is not None
            else f"{mode.capitalize()} • {duration_minutes} min"
        )
        resolved_description = (
            description
            if description is not None
            else f"Ends {PomodoroEmbeds._format_relative_end_time(end_time)}"
        )
        embed = discord.Embed(
            title=resolved_title,
            description=resolved_description,
            color=discord.Colour.green(),
        )

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
