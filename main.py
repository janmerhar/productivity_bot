# https://www.youtube.com/watch?v=-D2CvmHTqbE
import importlib
import logging
import discord
import asyncio
from datetime import datetime
from discord.ext import commands

from config.env import env
from config.logger import setup_logging
from services.error_reporting import handle_app_command_error
from views.habit_dynamic_items import register_habit_dynamic_items
from views.pomodoro_dynamic_items import register_pomodoro_dynamic_items
from views.reminder_dynamic_items import register_reminder_dynamic_items
from views.stock_list_dynamic_items import register_stock_list_dynamic_items
from views.scheduled_job_dynamic_items import register_scheduled_job_dynamic_items
from views.stock_alert_dynamic_items import register_stock_alert_dynamic_items
from views.todo_list_directory_dynamic_items import (
    register_todo_list_directory_dynamic_items,
)

tick_disabled = env.get("TICK_DISABLED") == "true"
alias_disabled = env.get("ALIAS_DISABLED") == "true"
dev_mode = env.get("DEV_MODE") == "true"
dev_guild_id = env.get("DEV_GUILD_ID")


def _env_flag(name: str, default: bool = False) -> bool:
    raw_value = env.get(name)
    if raw_value is None:
        return default
    return str(raw_value).strip().lower() in {"1", "true", "yes", "on"}

setup_logging()

intents = discord.Intents.default()
# intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

_sync_done = False
_global_sync_task: asyncio.Task | None = None
_import_prewarm_task: asyncio.Task | None = None


async def _sync_global_commands() -> None:
    try:
        synced = await bot.tree.sync()
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to sync global application commands"
        )
        return

    if dev_mode:
        logging.getLogger(__name__).info(
            "Synced %d global application commands (DEV_MODE).",
            len(synced),
        )
    else:
        logging.getLogger(__name__).info(
            "Synced %d global application commands.",
            len(synced),
        )


def _start_global_command_sync() -> None:
    global _global_sync_task
    if _global_sync_task is None or _global_sync_task.done():
        _global_sync_task = asyncio.create_task(_sync_global_commands())


async def _prewarm_imports() -> None:
    for module_name in ("yfinance", "openai"):
        try:
            await asyncio.to_thread(importlib.import_module, module_name)
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to prewarm import for %s",
                module_name,
            )


def _start_import_prewarm() -> None:
    global _import_prewarm_task
    if _import_prewarm_task is None or _import_prewarm_task.done():
        _import_prewarm_task = asyncio.create_task(_prewarm_imports())


@bot.event
async def on_ready():
    global _sync_done
    if not _sync_done:
        if not _env_flag("SYNC_COMMANDS_ON_START", default=True):
            logging.getLogger(__name__).info(
                "Skipping application command sync on startup."
            )
            _sync_done = True
            print("Online")
            _start_import_prewarm()
            return

        try:
            if dev_mode:
                if not dev_guild_id:
                    logging.getLogger(__name__).warning(
                        "DEV_MODE is true but DEV_GUILD_ID is not set; syncing global in background only."
                    )
                    _start_global_command_sync()
                else:
                    try:
                        guild_object = discord.Object(id=int(dev_guild_id))
                    except ValueError:
                        logging.getLogger(__name__).warning(
                            "DEV_GUILD_ID must be an integer; syncing global in background only."
                        )
                        _start_global_command_sync()
                    else:
                        bot.tree.clear_commands(guild=guild_object)
                        bot.tree.copy_global_to(guild=guild_object)
                        synced_guild = await bot.tree.sync(guild=guild_object)
                        logging.getLogger(__name__).info(
                            "Synced %d dev guild application commands for guild %s.",
                            len(synced_guild),
                            dev_guild_id,
                        )
                        _start_global_command_sync()
            else:
                _start_global_command_sync()
        except Exception:
            logging.getLogger(__name__).exception("Failed to sync application commands")
        else:
            _sync_done = True

    print(f"[{datetime.now().strftime('%H:%M')}] Online")
    _start_import_prewarm()


@bot.tree.error
async def on_app_command_error(interaction, error):
    await handle_app_command_error(interaction, error)


async def load():
    extensions = [
        "cogs.AutomationCog",
        "cogs.BugReportCog",
        "cogs.DailyTaskCog",
        "cogs.FeatureRequestCog",
        "cogs.HabitCog",
        "cogs.PomodoroCog",
        "cogs.ReminderCog",
        "cogs.RouterCog",
        "cogs.TodoCog",
        "cogs.TogglCog",
        "cogs.CryptoCog",
        "cogs.StocksCog",
    ]

    if not alias_disabled:
        extensions.append("cogs.AliasCog")

    if not tick_disabled:
        extensions.append("cogs.TickTickCog")

    for extension in extensions:
        await bot.load_extension(extension)


async def main():
    await load()
    await register_habit_dynamic_items(bot)
    await register_pomodoro_dynamic_items(bot)
    await register_reminder_dynamic_items(bot)
    await register_stock_list_dynamic_items(bot)
    await register_scheduled_job_dynamic_items(bot)
    await register_stock_alert_dynamic_items(bot)
    await register_todo_list_directory_dynamic_items(bot)
    await bot.start(env["DISCORD_TOKEN"])


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
