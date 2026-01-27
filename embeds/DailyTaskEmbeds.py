from typing import List

import discord


class DailyTaskEmbeds:
    @staticmethod
    def reminder_embed(message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Reminder",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}

    @staticmethod
    def job_embed(message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Scheduled Job",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}

    @staticmethod
    def jobs_list_embed(lines: List[str]) -> dict:
        embed = discord.Embed(
            title="Scheduled Jobs",
            color=discord.Colour.blurple(),
        )

        if not lines:
            embed.description = "No scheduled jobs found."
            return {"embed": embed}

        for index, line in enumerate(lines, start=1):
            label = line.lstrip("- ").strip()
            embed.add_field(name=f"Job {index}", value=label, inline=False)

        return {"embed": embed}

    @staticmethod
    def jobs_cancel_embed(message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Delete Job",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}
