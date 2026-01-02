# Color palette
# https://colorswall.com/palette/72717/
import asyncio
import discord
from discord.ext import commands
from discord import app_commands

from embeds.TogglEmbeds import TogglEmbeds
from classes.TogglCredentials import TogglCredentials


class TogglCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("TogglCog cog loaded")

    # Commands

    #
    # Authentication
    #
    @app_commands.command(name="aboutme", description="Toggl about me")
    async def aboutme(self, interaction: discord.Interaction):
        param = TogglEmbeds.aboutme_embed(
            interaction.guild_id,
            interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(
        name="togglkey", description="Save your Toggl API key for this server"
    )
    @app_commands.describe(api_key="Your Toggl API token")
    async def togglkey(self, interaction: discord.Interaction, api_key: str):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="Use this command inside a server to save your key.",
            )
            return

        cleaned = api_key.strip()
        if not cleaned:
            await interaction.response.send_message(
                ephemeral=True,
                content="API key cannot be empty.",
            )
            return

        await asyncio.to_thread(
            TogglCredentials.set_key,
            interaction.guild_id,
            interaction.user.id,
            cleaned,
        )
        await interaction.response.send_message(
            ephemeral=True,
            content="Saved your Toggl API key for this server.",
        )

    @app_commands.command(
        name="togglkeyclear",
        description="Remove your Toggl API key for this server",
    )
    async def togglkeyclear(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="Use this command inside a server to remove your key.",
            )
            return

        removed = await asyncio.to_thread(
            TogglCredentials.clear_key,
            interaction.guild_id,
            interaction.user.id,
        )
        message = (
            "Removed your Toggl API key for this server."
            if removed
            else "No Toggl API key was saved for this server."
        )
        await interaction.response.send_message(
            ephemeral=True,
            content=message,
        )

    #
    # Tracking
    #
    @app_commands.command(name="start", description="Toggl start timer")
    @app_commands.describe(
        project="Project that timer will start in",
        description="Description of this timer",
    )
    async def start(
        self,
        interaction: discord.Interaction,
        project: str = None,
        description: str = None,
    ):
        param = TogglEmbeds.start_embed(
            interaction.guild_id,
            interaction.user.id,
            project=project,
            description=description,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="timer", description="Toggl get active timer")
    async def timer(self, interaction: discord.Interaction):
        param = TogglEmbeds.timer_embed(
            interaction.guild_id,
            interaction.user.id,
        )
        await interaction.response.send_message(**param)

    @app_commands.command(name="stop", description="Toggl stop active time")
    async def stop(self, interaction: discord.Interaction):
        param = TogglEmbeds.stop_embed(
            interaction.guild_id,
            interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="inserttimer", description="Toggl insert past time")
    async def inserttimer(self, interaction: discord.Interaction):
        pass

    #
    # Saved timers
    # mongoDB
    #

    """
    - Improve tags handling
    """

    @app_commands.command(name="savetimer", description="Toggl save timer")
    @app_commands.describe(
        command="Name of the saved timer",
        workspace_id="Workspace id",
        billable="Billable",
        description="Description of the saved timer",
        pid="Project id",
        tags="Tags, separated by whitespaces",
        tid="Tid",
    )
    async def savetimer(
        self,
        interaction: discord.Interaction,
        command: str,
        workspace_id: int = None,
        billable: str = None,
        description: str = None,
        pid: int = None,
        tags: str = None,
        tid: int = None,
    ):
        param = TogglEmbeds.savetimer_embed(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            command=command,
            workspace_id=workspace_id,
            billable=billable,
            description=description,
            pid=pid,
            tags=tags,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="removetimer", description="Toggl remove saved timer")
    @app_commands.describe(identifier="Timer to be removed")
    async def removetimer(self, interaction: discord.Interaction, identifier: str):
        param = TogglEmbeds.removetimer_embed(
            identifier=identifier,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="startsaved", description="Toggl start saved timer")
    @app_commands.describe(identifier="Saved timer to start")
    async def startsaved(self, interaction: discord.Interaction, identifier: str):
        param = TogglEmbeds.startsaved_embed(
            identifier=identifier,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @startsaved.autocomplete("identifier")
    async def starsaved_autocomplete(
        self, interaction: discord.Interaction, current: str = ""
    ):
        options = TogglEmbeds.startsaved_autocomplete_embed(
            current=current,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        return options

    @app_commands.command(name="populartimers", description="Toggl most popular timers")
    @app_commands.describe(n="Number of most popular timers to be displayed")
    async def populartimers(self, interaction: discord.Interaction, n: int = 5):
        param = TogglEmbeds.populartimers_embed(
            n=n,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="timerhistory", description="Toggl get timer history")
    @app_commands.describe(n="Number of timers to display")
    async def timerhistory(self, interaction: discord.Interaction, n: int):
        param = TogglEmbeds.timerhistory_embed(
            n=n,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    #
    # Projects
    #
    @app_commands.command(name="newproject", description="Toggl create new project")
    @app_commands.describe(name="Name of newly created project")
    async def newproject(self, interaction: discord.Interaction, name: str):
        param = TogglEmbeds.newproject_embed(
            name=name,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(
        name="workspaceprojects", description="Toggl get all projects"
    )
    async def workspaceprojects(self, interaction: discord.Interaction):
        param = TogglEmbeds.workspaceprojects_embed(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    @app_commands.command(name="getproject", description="Toggl get project by id")
    @app_commands.describe(project_id="Project id")
    async def getproject(self, interaction: discord.Interaction, project_id: int):
        param = TogglEmbeds.getproject_embed(
            project_id=project_id,
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
        )

        await interaction.response.send_message(**param)

    #
    # Shortcuts
    #

    def getFunctionByName(self, name):
        try:
            fn = getattr(self, f"{name}")
            return fn
        except:
            return None

    def getDefaultParameters(self, cog_fn):
        return {
            param.name: param.default
            for param in cog_fn.parameters
            if param.default is not None
            and type(param.default) != discord.utils._MissingSentinel
        }

    """
    """

    @app_commands.command(name="createalias", description="create alias")
    @app_commands.describe(
        command="Command name",
        alias="Alias for the command",
        arguments="Semicolon separated arguments",
    )
    async def createalias(
        self,
        interaction: discord.Interaction,
        command: str,
        alias: str,
        arguments: str = "",
    ):
        cog_fn = self.getFunctionByName(name=command)
        cog_param = self.getDefaultParameters(cog_fn=cog_fn)

        param = TogglEmbeds.createalias_embed(
            guild_id=interaction.guild_id,
            user_id=interaction.user.id,
            command=command,
            alias=alias,
            arguments=arguments,
            cog_param=cog_param,
        )

        await interaction.response.send_message(**param)


async def setup(client):
    await client.add_cog(TogglCog(client))
