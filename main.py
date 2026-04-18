# https://www.youtube.com/watch?v=-D2CvmHTqbE
import importlib
import logging
import discord
import asyncio
from datetime import datetime
from discord.ext import commands

from config.env import settings
from config.logger import setup_logging
from services.error_reporting import handle_app_command_error
from views.habit_dynamic_items import register_habit_dynamic_items
from views.pomodoro_dynamic_items import register_pomodoro_dynamic_items
from views.reminder_dynamic_items import register_reminder_dynamic_items
from views.stock_list_dynamic_items import register_stock_list_dynamic_items
from views.scheduled_job_dynamic_items import register_scheduled_job_dynamic_items
from views.stock_alert_dynamic_items import register_stock_alert_dynamic_items
from views.stock_action_dynamic_items import register_stock_action_dynamic_items
from views.crypto_action_dynamic_items import register_crypto_action_dynamic_items
from views.todo_list_directory_dynamic_items import (
    register_todo_list_directory_dynamic_items,
)
from views.todo_list_description_dynamic_items import (
    register_todo_list_description_dynamic_items,
)
from views.todo_list_items_dynamic_items import register_todo_list_items_dynamic_items
from views.toggl_dynamic_items import register_toggl_dynamic_items

tick_disabled = settings.tick_disabled
alias_disabled = settings.alias_disabled
dev_mode = settings.dev_mode
dev_guild_id = settings.dev_guild_id
_runtime_sync_commands_on_start: bool | None = None


def configure_runtime(*, sync_commands_on_start: bool | None = None) -> None:
    global _runtime_sync_commands_on_start
    _runtime_sync_commands_on_start = sync_commands_on_start


def should_sync_commands_on_start() -> bool:
    if _runtime_sync_commands_on_start is not None:
        return _runtime_sync_commands_on_start
    return settings.sync_commands_on_start

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
        if not should_sync_commands_on_start():
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
                    guild_object = discord.Object(id=dev_guild_id)
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
    await register_stock_action_dynamic_items(bot)
    await register_crypto_action_dynamic_items(bot)
    await register_todo_list_directory_dynamic_items(bot)
    await register_todo_list_description_dynamic_items(bot)
    await register_todo_list_items_dynamic_items(bot)
    await register_toggl_dynamic_items(bot)
    await bot.start(settings.discord_token)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
