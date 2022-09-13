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
        fmt = await ctx.bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"Synced {len(fmt)} commands to thhe current guild.")
        return

    @app_commands.command(name="choosecolor", description="color selector")
    async def choosecolor(self, interaction: discord.Interaction, color:str):
        await interaction.response.send_message(f"Color selected: {color}")

async def setup(bot):
    await bot.add_cog(Color(bot), guilds=[discord.Object(id=864242668066177044)])