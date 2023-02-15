from re import A
from typing import Dict, Optional
import discord
from discord.ext import commands
from discord import app_commands
import inspect

from classes.TickTickFunctions import TickTickFunctions
from abstract.EmbedsAbstract import EmbedsAbstract  # Se moram implemenetirati

from dotenv import dotenv_values
env = dotenv_values(".env")


class TickTickEmbeds(EmbedsAbstract):
    pass
