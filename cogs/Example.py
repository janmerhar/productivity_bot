# https://www.youtube.com/watch?v=-D2CvmHTqbE
import discord
from discord.ext import commands
from discord import app_commands

class Color(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print("Color cog loaded")

    @commands.command()
    async def sync(self, ctx):
        """Sync slash commands to the guild and clear stale global commands."""
        # Remove old global commands so Discord stops offering outdated options
        ctx.bot.tree.clear_commands(guild=None)
        global_sync = await ctx.bot.tree.sync(guild=None)

        guild_sync = await ctx.bot.tree.sync(guild=ctx.guild)
        await ctx.send(
            "Synced {guild_count} guild command(s); cleared {global_count} global command(s).".format(
                guild_count=len(guild_sync),
                global_count=len(global_sync),
            )
        )
        return

    @app_commands.command(name="choosecolor", description="color selector")
    async def choosecolor(self, interaction: discord.Interaction, color:str):
        await interaction.response.send_message(f"Color selected: {color}")

async def setup(bot):
    await bot.add_cog(Color(bot), guilds=[discord.Object(id=864242668066177044)])
