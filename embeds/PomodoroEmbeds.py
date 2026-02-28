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
    ) -> dict:
        embed = discord.Embed(
            title="Pomodoro Scheduled",
            description=f"{mode.capitalize()} timer started.",
            color=discord.Colour.green(),
        )
        embed.add_field(name="Mode", value=mode.capitalize(), inline=True)
        embed.add_field(
            name="Duration", value=f"{duration_minutes} minutes", inline=True
        )
        embed.add_field(
            name="Ends",
            value=PomodoroEmbeds._format_relative_end_time(end_time),
            inline=True,
        )

        return {"embed": embed}

    @staticmethod
    def timer_complete_embed(
        mode: str,
        duration_minutes: Union[int, str],
        end_time: Optional[datetime.datetime],
        user_id: Optional[Union[int, str]],
    ) -> dict:
        embed = discord.Embed(
            title="Pomodoro Complete",
            description=f"{mode.capitalize()} timer finished.",
            color=discord.Colour.green(),
        )
        embed.add_field(name="Mode", value=mode.capitalize(), inline=True)
        embed.add_field(
            name="Duration", value=f"{duration_minutes} minutes", inline=True
        )
        embed.add_field(
            name="Ends at",
            value=PomodoroEmbeds._format_end_time(end_time),
            inline=True,
        )

        payload = {"embed": embed}
        if user_id:
            payload["content"] = f"<@{user_id}>"
        return payload

    @staticmethod
    def timer_stopped_embed(status_message: str) -> dict:
        embed = discord.Embed(
            title="Pomodoro Stopped",
            description="Your pomodoro timer has been stopped.",
            color=discord.Colour.orange(),
        )
        embed.add_field(name="Status", value=status_message, inline=False)
        embed.add_field(
            name="Next",
            value="Start a new focus or break timer using the buttons below.",
            inline=False,
        )
        return {"embed": embed}
