from embeds.TogglEmbeds import TogglEmbeds
from re import A
from typing import Dict, List, Optional
import discord
from discord.ext import commands
from discord import app_commands

from classes.AliasFunctions import AliasFunctions
from dotenv import dotenv_values

env = dotenv_values(".env")

tick_disabled = env.get("TICK_DISABLED") == "true"


class AliasEmbeds:
    def __init__(self):
        self.alias = AliasFunctions()

        self.toggl_embeds = TogglEmbeds()
        self.ticktick_embeds = None

        self.embed_classes = {"toggl": self.toggl_embeds}

        if not tick_disabled:
            from embeds.TickTickEmbeds import TickTickEmbeds

            self.ticktick_embeds = TickTickEmbeds()
            self.embed_classes["ticktick"] = self.ticktick_embeds

    def createalias_embed(self, command: str,  alias: str, arguments: str = ""):
        pass

    def usealias_embed(self, alias: str):
        # Iskanje, ce alias obstaja
        find_alias = self.alias.findAliases(identifier=alias)

        if len(find_alias) > 0:
            find_alias = find_alias[0]

            # Iskanje po embed_classes, ce obstaja komanda
            # Tale if stavek gre notri, toda retun ne dela
            application = find_alias["application"]

            if application in self.embed_classes:
                alias_class = self.embed_classes[application]

                return alias_class.usealias_embed(alias=alias)

            if application == "ticktick" and tick_disabled:
                embed_disabled = discord.Embed(
                    title=":ballot_box_with_check: TickTick",
                    color=discord.Colour.from_str("#ffb301"),
                    description="TickTick integration is disabled."
                )

                embed_disabled.set_thumbnail(
                    url="https://dashboard.snapcraft.io/site_media/appmedia/2022/02/icon_2XdTt7H.png"
                )

                return {"embeds": [embed_disabled]}

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

    def findaliases_embed(self, alias: str = ""):
        found_aliases = self.alias.findAliases(identifier=alias)

        embed = discord.Embed(
            title=f"Found {len(found_aliases)} aliases",
            color=0x00ff00
        )

        return {"embeds": [AliasEmbeds.aliasesToEmbed(found_aliases, embed)]}

    def popularalias_embed(self, n: int = 5):
        found_aliases = self.alias.findAliases(identifier="", n=n)

        embed = discord.Embed(
            title=f"Top {len(found_aliases)} aliases",
            color=0x00ff00
        )

        return {"embeds": [AliasEmbeds.aliasesToEmbed(found_aliases, embed)]}

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

    def aliasToEmbed(alias: object, embed):
        embed.add_field(name="Alias name",
                        value=alias["alias"], inline=False)
        embed.add_field(name="Slash command",
                        value=alias["command"], inline=False)
        embed.add_field(name="Application",
                        value=alias["application"], inline=False)
        embed.add_field(name="Parameters",
                        value=str(alias["param"]), inline=False)

        return embed
