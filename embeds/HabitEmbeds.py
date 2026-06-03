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
        reminder_time: Optional[datetime.time] = None,
    ) -> dict:
        name = str(habit.get("name") or "Habit")
        description = str(habit.get("description") or "").strip()
        created = habit.get("created")
        normalized_status = str(status or "").strip().lower()

        color_map = {
            "complete": discord.Colour.green(),
            "skip": discord.Colour.light_grey(),
            "incomplete": discord.Colour.orange(),
        }
        color = color_map.get(normalized_status, discord.Colour.blurple())

        embed = discord.Embed(title=name, color=color)
        embed.set_author(name="🏃 Habit")

        if description and description.lower() != name.lower():
            embed.description = description

        status_chips = {
            "complete": "✅ Complete",
            "skip": "⏭️ Skipped",
            "incomplete": "❌ Incomplete",
        }
        status_chip = status_chips.get(normalized_status, "⬜ Not tracked")
        embed.add_field(name="Today", value=status_chip, inline=True)

        if reminder_time is not None:
            time_str = reminder_time.strftime("%I:%M %p").lstrip("0") or reminder_time.strftime("%I:%M %p")
            embed.add_field(name="Reminder", value=time_str, inline=True)

        if progress:
            emojis = [HabitEmbeds._PROGRESS_EMOJI.get(mode, "❌") for mode in progress]
            embed.add_field(
                name=f"Last {len(progress)} {'day' if len(progress) == 1 else 'days'}",
                value=" ".join(emojis),
                inline=False,
            )

        return {"embed": embed}

    @staticmethod
    def progress_line(progress: list[str]) -> str:
        emojis = [HabitEmbeds._PROGRESS_EMOJI.get(mode, "❌") for mode in progress]
        days = len(progress)
        label = "Last 1 day" if days == 1 else f"Last {days} days"
        return f"{label}:\n{' '.join(emojis)}"

    @staticmethod
    def habit_reminder_payload(habit: Dict[str, Any]) -> dict:
        from classes.HabitFunctions import HabitFunctions
        from views.HabitActionView import HabitActionView

        name = str(habit.get("name") or "Habit")
        user_id = habit.get("user_id")
        habit_id = str(habit.get("_id") or "")

        payload = HabitEmbeds.habit_item_embed(
            habit,
            HabitFunctions.today_status(habit),
            HabitFunctions.recent_progress(habit, days=5),
        )
        if habit_id and user_id:
            payload["view"] = HabitActionView(
                habit_id,
                name,
                int(user_id),
                today_status=HabitFunctions.today_status(habit),
            )
        return payload
