import discord
from discord.ext import commands
from discord import app_commands

from classes.TogglFunctions import TogglFunctions
from dotenv import dotenv_values
env = dotenv_values(".env")


class TogglEmbed:
    def __init__(self):
        self.toggl = TogglFunctions(env["TOGGL_TOKEN"])
