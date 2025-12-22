from typing import List

import discord


class DailyTaskEmbeds:
    def reminder_embed(self, message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Reminder",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}

    def job_embed(self, message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Scheduled Job",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}

    def jobs_list_embed(self, lines: List[str]) -> dict:
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

    def jobs_cancel_embed(self, message: str, ok: bool) -> dict:
        embed = discord.Embed(
            title="Cancel Job",
            description=message,
            color=discord.Colour.green() if ok else discord.Colour.red(),
        )
        return {"embed": embed}
