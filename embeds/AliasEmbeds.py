from embeds.TogglEmbeds import TogglEmbeds
from embeds.TickTickEmbeds import TickTickEmbeds
from re import A
from typing import Dict, List, Optional
import discord
from discord.ext import commands
from discord import app_commands

from classes.AliasFunctions import AliasFunctions
from dotenv import dotenv_values
env = dotenv_values(".env")


class AliasEmbeds:
    def __init__(self):
        self.alias = AliasFunctions()

        self.toggl_embeds = TogglEmbeds()
        self.ticktick_embeds = TickTickEmbeds()

        self.embed_classes = {"toggl": self.toggl_embeds,
                              "ticktick": self.ticktick_embeds}

