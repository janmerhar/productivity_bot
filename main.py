# https://www.youtube.com/watch?v=-D2CvmHTqbE
import logging
import discord
import asyncio
from discord.ext import commands

from config.env import env
from config.logger import setup_logging

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
                        "DEV_MODE is true but DEV_GUILD_ID is not set; skipping sync."
                    )
                else:
                    try:
                        guild_object = discord.Object(id=int(dev_guild_id))
                    except ValueError:
                        logging.getLogger(__name__).warning(
                            "DEV_GUILD_ID must be an integer; skipping sync."
                        )
                    else:
                        bot.tree.copy_global_to(guild=guild_object)
                        synced = await bot.tree.sync(guild=guild_object)
                        did_sync = True
                        logging.getLogger(__name__).info(
                            "Synced %d dev guild application commands for guild %s.",
                            len(synced),
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


async def load():
    extensions = [
        "cogs.AliasCog",
        "cogs.DailyTaskCog",
        "cogs.HabitCog",
        "cogs.PomodoroCog",
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
