import discord


class SettingsEmbeds:
    @staticmethod
    def info_embed() -> discord.Embed:
        embed = discord.Embed(
            title="Productivity Bot",
            description=(
                "A self-hosted Discord bot for managing your time, tasks, and focus. "
                "Here's what you can do:"
            ),
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Time Tracking",
            value="`/toggl` — start, stop, and review Toggl timers and projects",
            inline=False,
        )
        embed.add_field(
            name="Reminders & Scheduled Jobs",
            value=(
                "`/reminder` — one-time reminders in natural language or cron\n"
                "`/job` — recurring jobs that post messages or market updates"
            ),
            inline=False,
        )
        embed.add_field(
            name="To-Do Lists",
            value="`/todo` — create and manage personal to-do lists",
            inline=False,
        )
        embed.add_field(
            name="Habits",
            value="`/habit` — track daily habits and streaks",
            inline=False,
        )
        embed.add_field(
            name="Focus Timer",
            value="`/pomodoro` — run timed focus and break sessions",
            inline=False,
        )
        embed.add_field(
            name="Market Data",
            value="`/stock` and `/crypto` — live prices and alerts",
            inline=False,
        )
        embed.add_field(
            name="Feedback",
            value="`/bug report` and `/feature request` — send feedback to the bot author",
            inline=False,
        )
        embed.add_field(
            name="Getting Started",
            value=(
                "1. Set your timezone: `/settings set timezone`\n"
                "2. Connect Toggl *(optional)*: `/settings set toggl`"
            ),
            inline=False,
        )
        return embed
