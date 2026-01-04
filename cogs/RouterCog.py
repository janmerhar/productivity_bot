import discord
from discord import app_commands
from discord.ext import commands

from classes.SlashCommandRouter import SlashCommandRouter


class RouterCog(commands.Cog):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("RouterCog cog loaded")

    @app_commands.command(
        name="run",
        description="Run an existing slash command from natural language",
    )
    @app_commands.describe(
        query="Instruction for the bot",
        private="Send the response privately",
    )
    async def run(
        self,
        interaction: discord.Interaction,
        query: str,
        private: bool = True,
    ) -> None:
        await interaction.response.defer(thinking=True, ephemeral=private)
        router = SlashCommandRouter(
            interaction.client.tree,
            excluded={"run"},
        )
        await router.dispatch(interaction, query, ephemeral_default=private)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(RouterCog(client))
