import discord
from discord.ext import commands
from discord import app_commands

from classes.TogglFunctions import TogglFunctions
from dotenv import dotenv_values
env = dotenv_values(".env")


class TogglEmbeds:
    def __init__(self):
        self.toggl = TogglFunctions(env["TOGGL_TOKEN"])

    def aboutme_embed(self) -> dict:
        data = self.toggl.aboutMe()

        embed = discord.Embed(
            title=":stopwatch: Toggl About Me",
            color=0xdf80c7
        )
        embed.set_thumbnail(
            url="https://assets.track.toggl.com/images/profile.png"
        )

        embed.add_field(name="ID", value=data["id"], inline=False)
        embed.add_field(name="Email", value=data["email"], inline=False)
        embed.add_field(name="Full name", value=data["fullname"], inline=False)

        embed.add_field(name="Timezone", value=data["timezone"], inline=False)
        embed.add_field(name="Registration date",
                        value=data["created_at"], inline=False)
        embed.add_field(name="Default workspace ID",
                        value=data["default_workspace_id"], inline=False)

        return {"embed": embed}
