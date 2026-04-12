# https://www.youtube.com/watch?v=-D2CvmHTqbE
import os
import platform
import sys
import logging


def _seed_windows_uname_cache() -> None:
    # Work around a very slow stdlib WMI lookup inside platform.win32_ver(),
    # which aiohttp triggers during import via platform.system().
    if os.name != "nt" or getattr(platform, "_uname_cache", None) is not None:
        return

    try:
        winver = sys.getwindowsversion()
        version_tuple = getattr(winver, "platform_version", None) or tuple(winver[:3])
        version = ".".join(str(part) for part in version_tuple)
        release = str(
            getattr(winver, "major", version_tuple[0] if version_tuple else "")
        )
        node = os.environ.get("COMPUTERNAME", "")
        machine = (
            os.environ.get("PROCESSOR_ARCHITEW6432")
            or os.environ.get("PROCESSOR_ARCHITECTURE", "")
        )
        platform._uname_cache = platform.uname_result(
            "Windows", node, release, version, machine
        )
    except Exception:
        pass


_seed_windows_uname_cache()

import discord
import asyncio
from discord.ext import commands

from config.env import env
from config.logger import setup_logging
from services.error_reporting import handle_app_command_error

tick_disabled = env.get("TICK_DISABLED") == "true"
dev_mode = env.get("DEV_MODE") == "true"
dev_guild_id = env.get("DEV_GUILD_ID")

setup_logging()

intents = discord.Intents.default()
# intents.message_content = True
bot = commands.Bot(command_prefix=".", intents=intents)

_sync_done = False


@bot.event
async def on_ready():
    global _sync_done
    if not _sync_done:
        did_sync = False
        try:
            if dev_mode:
                if not dev_guild_id:
                    logging.getLogger(__name__).warning(
                        "DEV_MODE is true but DEV_GUILD_ID is not set; syncing global only."
                    )
                    synced = await bot.tree.sync()
                    did_sync = True
                    logging.getLogger(__name__).info(
                        "Synced %d global application commands (DEV_MODE).",
                        len(synced),
                    )
                else:
                    try:
                        guild_object = discord.Object(id=int(dev_guild_id))
                    except ValueError:
                        logging.getLogger(__name__).warning(
                            "DEV_GUILD_ID must be an integer; skipping sync."
                        )
                    else:
                        synced_global = await bot.tree.sync()
                        bot.tree.clear_commands(guild=guild_object)
                        bot.tree.copy_global_to(guild=guild_object)
                        synced_guild = await bot.tree.sync(guild=guild_object)
                        did_sync = True
                        logging.getLogger(__name__).info(
                            "Synced %d global application commands (DEV_MODE).",
                            len(synced_global),
                        )
                        logging.getLogger(__name__).info(
                            "Synced %d dev guild application commands for guild %s.",
                            len(synced_guild),
                            dev_guild_id,
                        )
            else:
                await bot.tree.sync()
                did_sync = True
                logging.getLogger(__name__).info("Synced global application commands.")
        except Exception:
            logging.getLogger(__name__).exception("Failed to sync application commands")
        else:
            if did_sync:
                _sync_done = True

    print("Online")


@bot.tree.error
async def on_app_command_error(interaction, error):
    await handle_app_command_error(interaction, error)


async def load():
    extensions = [
        "cogs.AliasCog",
        "cogs.AutomationCog",
        "cogs.BugReportCog",
        "cogs.DailyTaskCog",
        "cogs.FeatureRequestCog",
        "cogs.HabitCog",
        "cogs.PomodoroCog",
        "cogs.RouterCog",
        "cogs.TodoCog",
        "cogs.TogglCog",
        "cogs.CryptoCog",
        "cogs.StocksCog",
    ]

    if not tick_disabled:
        extensions.append("cogs.TickTickCog")

    for extension in extensions:
        await bot.load_extension(extension)


async def main():
    await load()
    await bot.start(env["DISCORD_TOKEN"])


asyncio.run(main())
