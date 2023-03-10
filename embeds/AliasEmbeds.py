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

    def usealias_embed(self, alias: str):
        # Iskanje, ce alias obstaja
        find_alias = self.alias.findAliases(identifier=alias)

        if len(find_alias) > 0:
            find_alias = find_alias[0]

            # Iskanje po embed_classes, ce obstaja komanda
            # Tale if stavek gre notri, toda retun ne dela
            if find_alias["application"] in self.embed_classes:
                # TogglEmbeds object
                alias_class = self.embed_classes[find_alias["application"]]

                return alias_class.usealias_embed(alias=alias)

        # Nismo nasli alias
        # tukaj bom samo na koncu narredi en embed return

        embed_no_found = discord.Embed(
            title=":stopwatch: New alias",
            color=discord.Colour.from_str("#ff0000"),
            description="Alias command not found"
        )
        embed_no_found.set_thumbnail(
            url="https://i.imgur.com/Cmjl4Kb.png"
        )

        return {"embeds": [embed_no_found]}

    def aliasesToEmbed(aliases: List[object], embed):
        for alias in aliases:
            embed.add_field(name="Alias name",
                            value=alias["alias"], inline=True)
            embed.add_field(name="Slash command",
                            value=alias["command"], inline=True)
            embed.add_field(name="Application",
                            value=alias["application"], inline=True)
            embed.add_field(name="Number of runs",
                            value=alias["number_of_runs"], inline=True)
            embed.add_field(name="Number of runs",
                            value=alias["number_of_runs"], inline=True)
            embed.add_field(name="Parameters",
                            value=str(alias["param"]), inline=True)

        return embed
