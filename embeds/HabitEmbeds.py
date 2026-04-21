import datetime
from typing import Optional, Dict, Any

import discord


class HabitEmbeds:
    _PROGRESS_EMOJI = {
        "complete": "✅",
        "skip": "⏭️",
        "incomplete": "❌",
    }

    @staticmethod
    def _format_created(value: Optional[str]) -> str:
        if not value:
            return "Unknown"
        if isinstance(value, datetime.datetime):
            dt = value
        else:
            try:
                dt = datetime.datetime.fromisoformat(str(value))
            except ValueError:
                return str(value)
        try:
            return f"<t:{int(dt.timestamp())}:D>"
        except (OverflowError, OSError, ValueError):
            return dt.strftime("%Y-%m-%d")

    @staticmethod
    def _format_status(status: Optional[str]) -> str:
        if not status:
            return "Not set"
        label = status.replace("_", " ").strip()
        return label.capitalize() if label else "Not set"

    @staticmethod
    def insert_habit_embed(
        name: str,
        description: Optional[str],
        reminder_time: Optional[datetime.time],
    ) -> dict:
        embed = discord.Embed(
            title="Habit Created",
            color=discord.Colour.green(),
        )
        lines = []
        if description:
            lines.append(str(description))
        if reminder_time:
            lines.append(f"Reminder: {reminder_time.strftime('%H:%M')}")

        embed.add_field(
            name=name,
            value="\n".join(lines) if lines else "No details",
            inline=False,
        )
        return {"embed": embed}

    @staticmethod
    def habits_empty_embed(mode: str) -> dict:
        embed = discord.Embed(
            title="Habits",
            color=discord.Colour.blurple(),
        )
        if mode == "incomplete":
            embed.description = "No incomplete habits for today."
        elif mode == "skipped":
            embed.description = "No skipped habits for today."
        else:
            embed.description = "No habits found."
        return {"embed": embed}

    @staticmethod
    def deleted_habit_embed(name: str) -> dict:
        embed = discord.Embed(
            title=str(name or "Habit"),
            description="This habit was deleted.",
            color=discord.Colour.red(),
        )
        return {"embed": embed}

    @staticmethod
    def habit_item_embed(
        habit: Dict[str, Any],
        status: Optional[str],
        progress: Optional[list[str]] = None,
    ) -> dict:
        name = str(habit.get("name") or "Habit")
        description = habit.get("description")
        created = habit.get("created")

        embed = discord.Embed(
            title=name,
            color=discord.Colour.blurple(),
        )

        lines = []
        if description:
            lines.append(str(description))
        if created:
            lines.append(f"📅 {HabitEmbeds._format_created(created)}")
        lines.append(f"Today: {HabitEmbeds._format_status(status)}")
        if progress:
            lines.append(HabitEmbeds.progress_line(progress))

        embed.description = "\n".join(lines) if lines else "No details"
        return {"embed": embed}

    @staticmethod
    def progress_line(progress: list[str]) -> str:
        emojis = [HabitEmbeds._PROGRESS_EMOJI.get(mode, "❌") for mode in progress]
        days = len(progress)
        label = "Last 1 day" if days == 1 else f"Last {days} days"
        return f"{label}:\n{' '.join(emojis)}"

    @staticmethod
    def habit_reminder_payload(habit: Dict[str, Any]) -> dict:
        from views.HabitActionView import HabitActionView

        name = str(habit.get("name") or "Habit")
        description = habit.get("description")
        user_id = habit.get("user_id")
        habit_id = str(habit.get("_id") or "")

        embed = discord.Embed(
            title="Habit Reminder",
            color=discord.Colour.orange(),
        )
        lines = []
        if description:
            lines.append(str(description))
        embed.add_field(
            name=name,
            value="\n".join(lines) if lines else "No details",
            inline=False,
        )

        payload: Dict[str, Any] = {"embed": embed}
        if user_id:
            payload["content"] = f"<@{user_id}>"
        if habit_id and user_id:
            payload["view"] = HabitActionView(habit_id, name, int(user_id))
        return payload
