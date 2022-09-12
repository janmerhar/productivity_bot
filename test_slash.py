import discord
from discord import app_commands

from dotenv import dotenv_values, load_dotenv

env = dotenv_values(".env")


class aclient(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.synced = False
    
    async def on_ready(self):
        await self.wait_until_ready()
        if not self.synced:
            await tree.sync()
            self.synced = True
        print(f"We have logged in as {self.user}.")

client = aclient()
tree = app_commands.CommandTree(client)

@tree.command(name = "ping", description = "testing")
async def self(interaction: discord.Interaction, name: str):
    await interaction.response.send_message(f"Ping hello {name}! Koncno \ndelam ghahafhajksdhfkjsd")

@tree.command(name = "bruh", description = "testing")
async def self(interaction: discord.Interaction, name: str):
    await interaction.response.send_message(f" bruh {name}")

client.run(env["DISCORD_TOKEN"])