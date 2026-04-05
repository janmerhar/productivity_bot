# Color palette
# https://colorswall.com/palette/72717/
import asyncio
from typing import Callable, Optional

import discord
from discord.ext import commands
from discord import app_commands

from config.env import env
from embeds.TogglEmbeds import TogglEmbeds
from services.toggl_key_gate import ensure_toggl_api_key
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC, resolve_visibility
from views.TogglTimerHistoryView import TogglTimerHistoryView
from views.TogglTimerView import TogglTimerView

alias_disabled = env.get("ALIAS_DISABLED") == "true"
saved_disabled = "true"
DEFAULT_VISIBILITY = "public"


def _timer_description_from_message(message: discord.Message) -> str:
    content = str(message.clean_content or message.content or "").strip()
    if content:
        return content.splitlines()[0].strip()[:300]

    author_name = str(getattr(message.author, "display_name", "") or "Unknown").strip()
    if message.attachments:
        return f"Attachment from {author_name}"[:300]
    return f"Message from {author_name}"[:300]


@app_commands.context_menu(name="Start Timer")
async def start_timer_from_message(
    interaction: discord.Interaction,
    message: discord.Message,
) -> None:
    cog = interaction.client.get_cog("TogglCog")
    if cog is None:
        raise RuntimeError("TogglCog is not loaded.")

    description = _timer_description_from_message(message)
    await cog._execute_with_toggl_key(
        interaction,
        ephemeral=False,
        command_label="Start Timer",
        payload_builder=lambda: TogglEmbeds.start_embed(
            interaction.guild_id,
            interaction.user.id,
            description=description,
        ),
    )


class TogglCog(commands.Cog):
    toggl = app_commands.Group(name="toggl", description="Toggl commands")
    project = app_commands.Group(name="project", description="Manage Toggl projects")
    tag_group = app_commands.Group(name="tag", description="Manage Toggl timer tags")
    timer_group = app_commands.Group(name="timer", description="Manage Toggl timers")
    if not saved_disabled:
        saved = app_commands.Group(name="saved", description="Manage saved timers")
    if not alias_disabled:
        alias_group = app_commands.Group(
            name="alias", description="Manage Toggl aliases"
        )
    toggl.add_command(project)
    toggl.add_command(tag_group)
    toggl.add_command(timer_group)
    if not saved_disabled:
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
        payload = dict(payload)
        toggl_timer_view = payload.pop("_toggl_timer_view", None)
        if toggl_timer_view is not None:
            payload["view"] = TogglTimerView(**toggl_timer_view)
        toggl_timer_history_view = payload.pop("_toggl_timer_history_view", None)
        if toggl_timer_history_view is not None:
            payload["view"] = TogglTimerHistoryView(**toggl_timer_history_view)

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
    @toggl.command(name="account", description="Show your Toggl account")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def aboutme(
        self,
        interaction: discord.Interaction,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl account",
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
        billable="Whether this timer is billable",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def start(
        self,
        interaction: discord.Interaction,
        project: str = None,
        description: str = None,
        billable: Optional[bool] = None,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer start",
            payload_builder=lambda: TogglEmbeds.start_embed(
                interaction.guild_id,
                interaction.user.id,
                project=project,
                description=description,
                billable=billable,
            ),
        )

    @start.autocomplete("project")
    async def start_project_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = "",
    ) -> list[app_commands.Choice[str]]:
        return await asyncio.to_thread(
            TogglEmbeds.project_autocomplete_embed,
            current,
            interaction.guild_id,
            interaction.user.id,
        )

    @timer_group.command(name="active", description="Get active Toggl timer")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def timer(
        self,
        interaction: discord.Interaction,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer active",
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
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer stop",
            payload_builder=lambda: TogglEmbeds.stop_embed(
                interaction.guild_id,
                interaction.user.id,
            ),
        )

    @tag_group.command(name="add", description="Create a new Toggl tag")
    @app_commands.describe(
        name="Tag name",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def addtags(
        self,
        interaction: discord.Interaction,
        name: str,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl tag add",
            payload_builder=lambda: TogglEmbeds.tag_embed(
                interaction.guild_id,
                interaction.user.id,
                name=name,
            ),
        )

    @tag_group.command(name="show", description="Show a Toggl tag")
    @app_commands.describe(
        tag="Tag to show",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def showtag(
        self,
        interaction: discord.Interaction,
        tag: str,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl tag show",
            payload_builder=lambda: TogglEmbeds.tag_embed(
                interaction.guild_id,
                interaction.user.id,
                tag=tag,
            ),
        )

    @showtag.autocomplete("tag")
    async def showtag_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = "",
    ) -> list[app_commands.Choice[str]]:
        return await asyncio.to_thread(
            TogglEmbeds.tag_autocomplete_embed,
            current,
            interaction.guild_id,
            interaction.user.id,
        )

    @timer_group.command(name="insert", description="Insert past Toggl time")
    @app_commands.describe(
        project="Project for the inserted timer",
        description="Description of this timer",
        start="Start time, for example `yesterday 14:00`",
        stop="Stop time, for example `yesterday 16:30`",
        tags="Tags separated by spaces or commas",
        billable="Whether this timer is billable",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def inserttimer(
        self,
        interaction: discord.Interaction,
        start: str,
        stop: str,
        project: Optional[str] = None,
        description: Optional[str] = None,
        tags: Optional[str] = None,
        billable: Optional[bool] = None,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        locale_code = str(getattr(interaction, "locale", "") or "").strip() or None
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer insert",
            payload_builder=lambda: TogglEmbeds.inserttimer_embed(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                start=start,
                stop=stop,
                project=project,
                description=description,
                tags=tags,
                billable=billable,
                locale_code=locale_code,
            ),
        )

    @inserttimer.autocomplete("project")
    async def inserttimer_project_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = "",
    ) -> list[app_commands.Choice[str]]:
        return await self.start_project_autocomplete(interaction, current)

    #
    # Saved timers
    # mongoDB
    #

    """
    - Improve tags handling
    """

    if not saved_disabled:

        @saved.command(name="add", description="Save a timer preset")
        @app_commands.describe(
            command="Name of the saved timer",
            workspace_id="Workspace id",
            billable="Billable",
            description="Description of the saved timer",
            project="Project",
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
            project: str = None,
            tags: str = None,
            tid: int = None,
            visibility: str = DEFAULT_VISIBILITY,
        ):
            ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
            await self._execute_with_toggl_key(
                interaction,
                ephemeral=ephemeral,
                command_label="/toggl saved add",
                payload_builder=lambda: TogglEmbeds.savetimer_embed(
                    guild_id=interaction.guild_id,
                    user_id=interaction.user.id,
                    command=command,
                    workspace_id=workspace_id,
                    billable=billable,
                    description=description,
                    project=project,
                    tags=tags,
                ),
            )

        @savetimer.autocomplete("project")
        async def savetimer_project_autocomplete(
            self,
            interaction: discord.Interaction,
            current: str = "",
        ) -> list[app_commands.Choice[str]]:
            return await self.start_project_autocomplete(interaction, current)

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
            visibility: str = DEFAULT_VISIBILITY,
        ):
            ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
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
            visibility: str = DEFAULT_VISIBILITY,
        ):
            ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
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

        @saved.command(name="list", description="Most popular saved timers")
        @app_commands.describe(
            n="Number of most popular timers to be displayed",
            visibility=VISIBILITY_DESC,
        )
        @app_commands.choices(visibility=VISIBILITY_CHOICES)
        async def populartimers(
            self,
            interaction: discord.Interaction,
            n: int = 5,
            visibility: str = DEFAULT_VISIBILITY,
        ):
            ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
            await self._execute_with_toggl_key(
                interaction,
                ephemeral=ephemeral,
                command_label="/toggl saved list",
                payload_builder=lambda: TogglEmbeds.populartimers_embed(
                    n=n,
                    guild_id=interaction.guild_id,
                    user_id=interaction.user.id,
                ),
            )

    @timer_group.command(name="list", description="Get the last 5 Toggl timers")
    @app_commands.describe(
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def timerhistory(
        self,
        interaction: discord.Interaction,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl timer list",
            payload_builder=lambda: TogglEmbeds.timerhistory_embed(
                n=5,
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
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl project create",
            payload_builder=lambda: TogglEmbeds.project_embed(
                project=name,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
                create=True,
            ),
        )

    @project.command(name="list", description="List Toggl projects")
    @app_commands.describe(visibility=VISIBILITY_DESC)
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def workspaceprojects(
        self,
        interaction: discord.Interaction,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl project list",
            payload_builder=lambda: TogglEmbeds.workspaceprojects_embed(
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    @project.command(name="get", description="Get a Toggl project")
    @app_commands.describe(
        project="Project from autocomplete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def getproject(
        self,
        interaction: discord.Interaction,
        project: str,
        visibility: str = DEFAULT_VISIBILITY,
    ):
        ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
        await self._execute_with_toggl_key(
            interaction,
            ephemeral=ephemeral,
            command_label="/toggl project get",
            payload_builder=lambda: TogglEmbeds.project_embed(
                project=project,
                guild_id=interaction.guild_id,
                user_id=interaction.user.id,
            ),
        )

    @getproject.autocomplete("project")
    async def getproject_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str = "",
    ) -> list[app_commands.Choice[str]]:
        return await self.start_project_autocomplete(interaction, current)

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
            alias_map = {
                "about": "aboutme",
                "account": "aboutme",
                "timer start": "start",
                "timer stop": "stop",
                "timer current": "timer",
                "timer insert": "inserttimer",
                "timer list": "timerhistory",
                "project create": "newproject",
                "project list": "workspaceprojects",
                "project get": "getproject",
                "alias create": "createalias",
            }
            if not saved_disabled:
                alias_map.update(
                    {
                        "saved create": "savetimer",
                        "saved delete": "removetimer",
                        "saved start": "startsaved",
                        "saved popular": "populartimers",
                    }
                )
            return alias_map

        def getFunctionByName(self, name):
            key = self._normalize_alias_command(name)
            if not key:
                return None
            alias_map = self._alias_command_map()
            if key in alias_map:
                key = alias_map[key]
            elif " " in key:
                return None
            if saved_disabled and key in {
                "savetimer",
                "removetimer",
                "startsaved",
                "populartimers",
            }:
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
            visibility: str = DEFAULT_VISIBILITY,
        ):
            ephemeral = resolve_visibility(visibility, default=DEFAULT_VISIBILITY)
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
    client.tree.add_command(start_timer_from_message)
