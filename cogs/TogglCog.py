# Color palette
# https://colorswall.com/palette/72717/
import asyncio
from typing import Callable, Optional

import discord
from discord.ext import commands
from discord import app_commands

from config.env import env
from embeds.TogglEmbeds import TogglEmbeds
from services.error_reporting import ValidationError
from services.toggl_key_gate import ensure_toggl_api_key
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility

alias_disabled = env.get("ALIAS_DISABLED") == "true"


class TogglCog(commands.Cog):
    toggl = app_commands.Group(name="toggl", description="Toggl commands")
    project = app_commands.Group(name="project", description="Manage Toggl projects")
    timer_group = app_commands.Group(name="timer", description="Manage Toggl timers")
    saved = app_commands.Group(name="saved", description="Manage saved timers")
    if not alias_disabled:
        alias_group = app_commands.Group(name="alias", description="Manage Toggl aliases")
    toggl.add_command(project)
    toggl.add_command(timer_group)
    toggl.add_command(saved)
    if not alias_disabled:
        toggl.add_command(alias_group)

    def __init__(self, client):
        self.client = client

    # Events

    @commands.Cog.listener()
    async def on_ready(self):
        print("TogglCog cog loaded")

    async def _send_payload(
        self,
        interaction: discord.Interaction,
        payload: dict,
        ephemeral: bool,
    ) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return

        await interaction.response.send_message(ephemeral=ephemeral, **payload)

    async def _execute_with_toggl_key(
        self,
        interaction: discord.Interaction,
        *,
        ephemeral: bool,
        command_label: str,
        payload_builder: Callable[[], dict],
    ) -> None:
        if interaction.guild_id is None:
            raise ValidationError(
                "Use this command inside a server.",
                ephemeral=ephemeral,
            )

        async def _continue_with_key(
            followup_interaction: discord.Interaction,
            _api_key: str,
        ) -> None:
            payload = await asyncio.to_thread(payload_builder)
            await self._send_payload(followup_interaction, payload, ephemeral)

        api_key = await ensure_toggl_api_key(
            interaction,
            _continue_with_key,
            continue_message=f"Toggl API key saved. Continuing `{command_label}`.",
        )
        if api_key is None:
            return

        payload = await asyncio.to_thread(payload_builder)
        await self._send_payload(interaction, payload, ephemeral)

    # Commands

    #
    # Authentication
    #
    @toggl.command(name="about", description="About your Toggl account")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def aboutme(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl about",
            payload_builder=lambda: TogglEmbeds.aboutme_embed(
                interaction.guild_id,
                interaction.user.id,
            ),
        )

    #
    # Tracking
    #
    @timer_group.command(name="start", description="Start a Toggl timer")
    @app_commands.describe(
        project="Project that timer will start in",
        description="Description of this timer",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def start(
        self,
        interaction: discord.Interaction,
        project: str = None,
        description: str = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer start",
            payload_builder=lambda: TogglEmbeds.start_embed(
                interaction.guild_id,
                interaction.user.id,
                project=project,
                description=description,
            ),
        )

    @timer_group.command(name="current", description="Get active Toggl timer")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def timer(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer current",
            payload_builder=lambda: TogglEmbeds.timer_embed(
                interaction.guild_id,
                interaction.user.id,
            ),
        )

    @timer_group.command(name="stop", description="Stop active Toggl time")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def stop(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer stop",
            payload_builder=lambda: TogglEmbeds.stop_embed(
                interaction.guild_id,
                interaction.user.id,
            ),
        )

    @timer_group.command(name="insert", description="Insert past Toggl time")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def inserttimer(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        pass

    #
    # Saved timers
    # mongoDB
    #

    """
    - Improve tags handling
    """

    @saved.command(name="create", description="Save a timer preset")
    @app_commands.describe(
        command="Name of the saved timer",
        workspace_id="Workspace id",
        billable="Billable",
        description="Description of the saved timer",
        pid="Project id",
        tags="Tags, separated by whitespaces",
        tid="Tid",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
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
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl saved create",
            payload_builder=lambda: TogglEmbeds.savetimer_embed(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                command=command,
                workspace_id=workspace_id,
                billable=billable,
                description=description,
                pid=pid,
                tags=tags,
            ),
        )

    @saved.command(name="delete", description="Delete a saved timer")
    @app_commands.describe(
        identifier="Timer to be removed",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def removetimer(
        self,
        interaction: discord.Interaction,
        identifier: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl saved delete",
            payload_builder=lambda: TogglEmbeds.removetimer_embed(
                identifier=identifier,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    @saved.command(name="start", description="Start a saved timer")
    @app_commands.describe(
        identifier="Saved timer to start",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def startsaved(
        self,
        interaction: discord.Interaction,
        identifier: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl saved start",
            payload_builder=lambda: TogglEmbeds.startsaved_embed(
                identifier=identifier,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

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

    @saved.command(name="popular", description="Most popular saved timers")
    @app_commands.describe(
        n="Number of most popular timers to be displayed",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def populartimers(
        self,
        interaction: discord.Interaction,
        n: int = 5,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl saved popular",
            payload_builder=lambda: TogglEmbeds.populartimers_embed(
                n=n,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    @timer_group.command(name="history", description="Get Toggl timer history")
    @app_commands.describe(
        n="Number of timers to display",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def timerhistory(
        self,
        interaction: discord.Interaction,
        n: int,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer history",
            payload_builder=lambda: TogglEmbeds.timerhistory_embed(
                n=n,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    #
    # Projects
    #
    @project.command(name="create", description="Create a Toggl project")
    @app_commands.describe(
        name="Name of newly created project",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def newproject(
        self,
        interaction: discord.Interaction,
        name: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl project create",
            payload_builder=lambda: TogglEmbeds.newproject_embed(
                name=name,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    @project.command(name="list", description="List Toggl projects")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def workspaceprojects(
        self,
        interaction: discord.Interaction,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl project list",
            payload_builder=lambda: TogglEmbeds.workspaceprojects_embed(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    @project.command(name="get", description="Get a Toggl project by id")
    @app_commands.describe(
        project_id="Project id",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def getproject(
        self,
        interaction: discord.Interaction,
        project_id: int,
        visibility: Optional[app_commands.Choice[str]] = None,
    ):
        ephemeral = resolve_visibility(visibility, default="public")
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl project get",
            payload_builder=lambda: TogglEmbeds.getproject_embed(
                project_id=project_id,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    if not alias_disabled:

        @staticmethod
        def _normalize_alias_command(command: str) -> str:
            if not command:
                return ""
            cleaned = " ".join(command.strip().lower().split())
            if cleaned.startswith("toggl "):
                cleaned = cleaned[len("toggl ") :].strip()
            return cleaned

        @staticmethod
        def _alias_command_map() -> dict:
            return {
                "about": "aboutme",
                "timer start": "start",
                "timer stop": "stop",
                "timer current": "timer",
                "timer insert": "inserttimer",
                "timer history": "timerhistory",
                "saved create": "savetimer",
                "saved delete": "removetimer",
                "saved start": "startsaved",
                "saved popular": "populartimers",
                "project create": "newproject",
                "project list": "workspaceprojects",
                "project get": "getproject",
                "alias create": "createalias",
            }

        def getFunctionByName(self, name):
            key = self._normalize_alias_command(name)
            if not key:
                return None
            alias_map = self._alias_command_map()
            if key in alias_map:
                key = alias_map[key]
            elif " " in key:
                return None
            try:
                fn = getattr(self, f"{key}")
                return fn
            except:
                return None

        def getDefaultParameters(self, cog_fn):
            if cog_fn is None:
                return {}
            return {
                param.name: param.default
                for param in cog_fn.parameters
                if param.default is not None
                and type(param.default) != discord.utils._MissingSentinel
            }

        @alias_group.command(name="create", description="Create a Toggl alias")
        @app_commands.describe(
            command="Command name",
            alias="Alias for the command",
            arguments="Semicolon separated arguments",
            visibility=VISIBILITY_DESC,
        )
        @app_commands.choices(visibility=VISIBILITY_CHOICES)
        async def createalias(
            self,
            interaction: discord.Interaction,
            command: str,
            alias: str,
            arguments: str = "",
            visibility: Optional[app_commands.Choice[str]] = None,
        ):
            ephemeral = resolve_visibility(visibility, default="public")
            normalized_command = self._normalize_alias_command(command)
            if normalized_command:
                command = normalized_command
            cog_fn = self.getFunctionByName(name=command)
            cog_param = self.getDefaultParameters(cog_fn=cog_fn)
            await self._execute_with_toggl_key(
                interaction,
                ephemeral=ephemeral,
                command_label="/toggl alias create",
                payload_builder=lambda: TogglEmbeds.createalias_embed(
                    guild_id=interaction.guild_id,
                    user_id=interaction.user.id,
                    command=command,
                    alias=alias,
                    arguments=arguments,
                    cog_param=cog_param,
                ),
            )

async def setup(client):
    await client.add_cog(TogglCog(client))
