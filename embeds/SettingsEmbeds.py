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
                "Just start using commands — the bot will ask for your timezone "
                "and Toggl API key the first time they're needed.\n"
                "You can also set them manually: `/settings set timezone` · `/settings set toggl`"
            ),
            inline=False,
        )
        return embed

    @staticmethod
    def help_welcome_embed() -> discord.Embed:
        embed = discord.Embed(
            title="Productivity Bot",
            description=(
                "A productivity bot for individuals and teams — shared to-dos, reminders, "
                "habits, Pomodoro focus sessions, and Toggl time tracking, all in one place. "
                "Works in servers and DMs. Select a category below to explore."
            ),
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Where to Begin",
            value=(
                "Try `/todo add` to add a task, `/reminder add` to set a reminder, "
                "or `/habit add` to track a habit. "
                "The bot will ask for anything it needs as you go."
            ),
            inline=False,
        )
        embed.add_field(
            name="What's Available",
            value="📋 To-Do Lists · ⏰ Reminders · 🔁 Habits · 🍅 Pomodoro · ⏱ Time Tracking",
            inline=False,
        )
        embed.set_footer(text="Use the menu below to explore each feature")
        return embed

    @staticmethod
    def reference_embed() -> discord.Embed:
        embed = discord.Embed(
            title="Command Reference",
            description="All commands at a glance. Select a category for details.",
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="📋 To-Do Lists",
            value=(
                "`/todo add` · `/todo show` · `/todo edit`\n"
                "`/todo status` · `/todo complete` · `/todo delete` · `/todo assign`\n"
                "`/todo list show` · `/todo list browse` · `/todo list create`\n"
                "`/todo list edit` · `/todo list delete` · `/todo list clear`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⏰ Reminders",
            value=(
                "`/reminder add` · `/reminder list` · `/reminder show`\n"
                "`/reminder edit` · `/reminder delete` · `/reminder pause` · `/reminder resume`"
            ),
            inline=False,
        )
        embed.add_field(
            name="🔁 Habits",
            value="`/habit add` · `/habit list` · `/habit show` · `/habit edit` · `/habit delete`",
            inline=False,
        )
        embed.add_field(
            name="🍅 Pomodoro",
            value=(
                "`/pomodoro start` · `/pomodoro stop` · `/pomodoro pause`\n"
                "`/pomodoro resume` · `/pomodoro extend` · `/pomodoro active`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⏱ Time Tracking",
            value=(
                "`/toggl timer start` · `/toggl timer active` · `/toggl timer stop`\n"
                "`/toggl timer insert` · `/toggl timer list`\n"
                "`/toggl project create` · `/toggl project list` · `/toggl project show`\n"
                "`/toggl tag add` · `/toggl tag show`\n"
                "`/toggl saved add` · `/toggl saved start` · `/toggl saved list` · `/toggl saved delete`\n"
                "`/toggl account`"
            ),
            inline=False,
        )
        embed.add_field(
            name="⚙️ Settings",
            value="`/settings set timezone` · `/settings set toggl` · `/info`",
            inline=False,
        )
        return embed

    @staticmethod
    def todo_embed() -> discord.Embed:
        embed = discord.Embed(
            title="📋 To-Do Lists",
            description="Create personal or channel-level task lists and track items through their lifecycle.",
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Items",
            value=(
                "`/todo add` — Add an item to a list\n"
                "`/todo show` — View a todo's details\n"
                "`/todo edit` — Edit a todo\n"
                "`/todo status` — Update status\n"
                "`/todo complete` — Mark as done\n"
                "`/todo delete` — Delete a todo\n"
                "`/todo assign` — Assign or unassign an item"
            ),
            inline=False,
        )
        embed.add_field(
            name="Lists",
            value=(
                "`/todo list show` — Show items on a list\n"
                "`/todo list browse` — Browse available lists\n"
                "`/todo list create` — Create a new custom list\n"
                "`/todo list edit` — Edit a custom list\n"
                "`/todo list delete` — Delete a custom list\n"
                "`/todo list clear` — Remove all items from a list"
            ),
            inline=False,
        )
        embed.add_field(
            name="Context Menu Shortcuts",
            value=(
                "Right-click any message → **Add to Todo**\n"
                "Right-click any message → **Add to Personal Todo**"
            ),
            inline=False,
        )
        return embed

    @staticmethod
    def reminders_embed() -> discord.Embed:
        embed = discord.Embed(
            title="⏰ Reminders",
            description="Set one-time or repeating reminders using natural language or cron expressions.",
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Commands",
            value=(
                "`/reminder add` — Add a new reminder\n"
                "`/reminder list` — List your reminders\n"
                "`/reminder show` — View a reminder's details\n"
                "`/reminder edit` — Edit a reminder\n"
                "`/reminder delete` — Delete a reminder\n"
                "`/reminder pause` — Pause a reminder\n"
                "`/reminder resume` — Resume a paused reminder"
            ),
            inline=False,
        )
        embed.add_field(
            name="Context Menu Shortcut",
            value="Right-click any message → **Create Reminder**",
            inline=False,
        )
        return embed

    @staticmethod
    def habits_embed() -> discord.Embed:
        embed = discord.Embed(
            title="🔁 Habits",
            description="Track daily habits and build streaks over time.",
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Commands",
            value=(
                "`/habit add` — Add a new habit\n"
                "`/habit list` — List habits\n"
                "`/habit show` — View a habit's details and mark it\n"
                "`/habit edit` — Edit a habit\n"
                "`/habit delete` — Delete a habit"
            ),
            inline=False,
        )
        embed.add_field(
            name="Marking Habits",
            value="Open a habit with `/habit show` and use the Complete or Skip buttons.",
            inline=False,
        )
        return embed

    @staticmethod
    def pomodoro_embed() -> discord.Embed:
        embed = discord.Embed(
            title="🍅 Pomodoro Timer",
            description="Run timed focus sessions with optional breaks.",
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Commands",
            value=(
                "`/pomodoro start` — Start a focus timer\n"
                "`/pomodoro stop` — Stop the running timer\n"
                "`/pomodoro pause` — Pause the timer\n"
                "`/pomodoro resume` — Resume a paused timer\n"
                "`/pomodoro extend` — Extend the timer duration\n"
                "`/pomodoro active` — Show your running timer"
            ),
            inline=False,
        )
        embed.add_field(
            name="Context Menu Shortcut",
            value="Right-click any message → **Start Pomodoro**",
            inline=False,
        )
        return embed

    @staticmethod
    def toggl_embed() -> discord.Embed:
        embed = discord.Embed(
            title="⏱ Time Tracking",
            description="Manage Toggl timers, projects, and tags directly from Discord.",
            color=discord.Colour.blurple(),
        )
        embed.add_field(
            name="Timers",
            value=(
                "`/toggl timer start` — Start a Toggl timer\n"
                "`/toggl timer active` — Show your running timer\n"
                "`/toggl timer stop` — Stop the running timer\n"
                "`/toggl timer insert` — Log a past time entry\n"
                "`/toggl timer list` — Recent time entries"
            ),
            inline=False,
        )
        embed.add_field(
            name="Projects & Tags",
            value=(
                "`/toggl project create` — Create a project\n"
                "`/toggl project list` — List projects\n"
                "`/toggl project show` — Show a project\n"
                "`/toggl tag add` — Add a tag\n"
                "`/toggl tag show` — Show a tag"
            ),
            inline=False,
        )
        embed.add_field(
            name="Saved Timers",
            value=(
                "`/toggl saved add` — Save a timer preset\n"
                "`/toggl saved start` — Start a saved timer\n"
                "`/toggl saved list` — Browse saved timers\n"
                "`/toggl saved delete` — Delete a saved timer"
            ),
            inline=False,
        )
        embed.add_field(
            name="Account & Setup",
            value=(
                "`/toggl account` — Show your Toggl account\n"
                "Connect your account: `/settings set toggl`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Context Menu Shortcut",
            value="Right-click any message → **Start Timer**",
            inline=False,
        )
        return embed

