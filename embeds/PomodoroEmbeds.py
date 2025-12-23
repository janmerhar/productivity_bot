import datetime
from typing import Optional, Union

import discord


class PomodoroEmbeds:
    @staticmethod
    def _format_end_time(end_time: Optional[datetime.datetime]) -> str:
        if end_time is None:
            return "soon"
        return end_time.strftime("%H:%M")

    def insert_timer_embed(
        self,
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
            name="Ends at", value=self._format_end_time(end_time), inline=True
        )

        return {"embed": embed}

    def timer_complete_embed(
        self,
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
            name="Ends at", value=self._format_end_time(end_time), inline=True
        )

        payload = {"embed": embed}
        if user_id:
            payload["content"] = f"<@{user_id}>"
        return payload
