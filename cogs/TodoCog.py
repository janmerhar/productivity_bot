import asyncio
from typing import Optional, List, Dict, Any

import discord
from discord import app_commands
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from classes.UserSettingsFunctions import UserSettingsFunctions
from embeds.TodoEmbeds import TodoEmbeds, TodoListItemsView, TodoItemEditModal
from services.due_datetime import DueDateService
from services.discord_helpers import resolve_ephemeral_from_scope
from services.error_reporting import UserVisibleError, ValidationError
from services.timezone_gate import ensure_user_timezone
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC
from views.TodoListDescriptionView import TodoListDescriptionView


_SORT_CHOICES = [
    app_commands.Choice(name="Ascending", value="ascending"),
    app_commands.Choice(name="Descending", value="descending"),
]
_ADD_SCOPE_CHOICES = [
    app_commands.Choice(name="This Channel", value="channel"),
    app_commands.Choice(name="Personal", value="personal"),
]
_LIST_SCOPE_CHOICES = [
    app_commands.Choice(name="Server", value="server"),
    app_commands.Choice(name="Personal", value="personal"),
]
_LIST_DIRECTORY_SCOPE_CHOICES = [
    app_commands.Choice(name="Server", value="server"),
    app_commands.Choice(name="Personal", value="personal"),
]
_ITEM_STATUS_CHOICES = [
    app_commands.Choice(name="To Do", value="todo"),
    app_commands.Choice(name="In Progress", value="in_progress"),
    app_commands.Choice(name="Done", value="done"),
]
_YES_NO_CHOICES = [
    app_commands.Choice(name="Yes", value="yes"),
    app_commands.Choice(name="No", value="no"),
]
_LIST_STATUS_FILTER_CHOICES = [
    app_commands.Choice(name="All", value="all"),
    app_commands.Choice(name="To Do", value="todo"),
    app_commands.Choice(name="In Progress", value="in_progress"),
    app_commands.Choice(name="Done", value="done"),
]


@app_commands.context_menu(name="Add to Todo")
async def add_message_to_todo(
    interaction: discord.Interaction,
    message: discord.Message,
) -> None:
    scope_value = "channel" if interaction.guild_id is not None else "personal"
    ephemeral = scope_value == "personal"

    await interaction.response.defer(ephemeral=ephemeral)

    try:
        document = await asyncio.to_thread(
            TodoFunctions.insert_todo_from_message,
            interaction.guild_id,
            interaction.user.id,
            message.channel.id,
            getattr(message.channel, "name", None),
            message.content,
            message.author.display_name,
            bool(message.attachments),
            scope_value,
        )
    except ValueError as exc:
        raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
    except Exception as exc:
        raise UserVisibleError(
            "Something went wrong while creating that todo.",
            ephemeral=ephemeral,
            cause=exc,
        )

    try:
        todo_list = await asyncio.to_thread(
            TodoFunctions.fetch_todo_list_by_id,
            document.get("list_id"),
        )
    except Exception:
        todo_list = None

    payload = TodoEmbeds.item_details_embed(
        todo_list or {"name": "List"},
        document,
    )
    await interaction.followup.send(ephemeral=ephemeral, **payload)


@app_commands.context_menu(name="Add to Personal Todo")
async def add_message_to_personal_todo(
    interaction: discord.Interaction,
    message: discord.Message,
) -> None:
    await interaction.response.defer(ephemeral=True)

    try:
        document = await asyncio.to_thread(
            TodoFunctions.insert_todo_from_message,
            interaction.guild_id,
            interaction.user.id,
            message.channel.id,
            getattr(message.channel, "name", None),
            message.content,
            message.author.display_name,
            bool(message.attachments),
            "personal",
        )
    except ValueError as exc:
        raise ValidationError(str(exc), ephemeral=True, cause=exc)
    except Exception as exc:
        raise UserVisibleError(
            "Something went wrong while creating that todo.",
            ephemeral=True,
            cause=exc,
        )

    try:
        todo_list = await asyncio.to_thread(
            TodoFunctions.fetch_todo_list_by_id,
            document.get("list_id"),
        )
    except Exception:
        todo_list = None

    payload = TodoEmbeds.item_details_embed(
        todo_list or {"name": "List"},
        document,
    )
    await interaction.followup.send(ephemeral=True, **payload)


class TodoCog(commands.Cog):
    todo_group = app_commands.Group(name="todo", description="Manage to-dos")
    list_group = app_commands.Group(name="list", description="Manage todo lists")
    todo_group.add_command(list_group)

    def __init__(self, client: commands.Bot) -> None:
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print("TodoCog cog loaded")

    @staticmethod
    def _custom_list_option_label(todo_list: Dict[str, Any]) -> str:
        name = str(todo_list.get("name") or "Unnamed").strip() or "Unnamed"
        scope_value = TodoFunctions._normalize_scope(str(todo_list.get("scope") or ""))
        if scope_value == "personal":
            return f"Personal / {name}"[:100]
        if todo_list.get("channel_id") is None:
            return f"Server / {name}"[:100]
        return f"This Channel / {name}"[:100]

    async def _validate_list_access(
        self,
        interaction: discord.Interaction,
        todo_list: Dict[str, Any],
    ) -> None:
        scope_value = TodoFunctions._normalize_scope(str(todo_list.get("scope") or ""))
        if scope_value == "personal":
            owner_id = int(todo_list.get("user_id") or 0)
            if owner_id != interaction.user.id:
                raise ValidationError(
                    "That personal list is not available to you.",
                    ephemeral=True,
                )
            return

        guild_id = todo_list.get("guild_id")
        if interaction.guild_id != guild_id:
            raise ValidationError(
                "That list is not in this server.",
                ephemeral=True,
            )

        channel_id = todo_list.get("channel_id")
        if channel_id is None or interaction.guild is None:
            return

        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            raise ValidationError(
                "That list's channel was not found.",
                ephemeral=True,
            )

    async def _resolve_list_target(
        self,
        interaction: discord.Interaction,
        list_target: Optional[str],
        *,
        allow_all_server: bool = False,
    ) -> tuple[Optional[Dict[str, Any]], str, bool]:
        target_value = (list_target or "").strip()
        if not target_value:
            target_value = "channel" if interaction.guild_id is not None else "personal"

        if interaction.guild_id is None and (
            target_value in {"channel", "all_server"} or target_value.startswith("channel:")
        ):
            target_value = "personal"

        if target_value == "all_server":
            if not allow_all_server or interaction.guild_id is None:
                raise ValidationError(
                    "All server channels is only available in servers.",
                    ephemeral=True,
                )
            return None, "channel", True

        if target_value == "personal":
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                "personal",
            )
            return todo_list, "personal", False

        if target_value == "channel":
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                "channel",
            )
            return todo_list, "channel", False

        if target_value.startswith("channel:"):
            try:
                selected_channel_id = int(target_value.split(":", 1)[1])
            except (ValueError, IndexError):
                raise ValidationError(
                    "Please select a valid channel from autocomplete.",
                    ephemeral=True,
                )
            if interaction.guild is None:
                raise ValidationError(
                    "Channel targets are only available in servers.",
                    ephemeral=True,
                )
            selected_channel = interaction.guild.get_channel(selected_channel_id)
            if selected_channel is None:
                raise ValidationError(
                    "That channel was not found.",
                    ephemeral=True,
                )
            if not isinstance(selected_channel, discord.TextChannel):
                raise ValidationError(
                    "Please select a text channel from autocomplete.",
                    ephemeral=True,
                )
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_channel_list,
                interaction.guild_id,
                selected_channel_id,
                interaction.user.id,
                getattr(selected_channel, "name", None),
            )
            return todo_list, "channel", False

        todo_list = await asyncio.to_thread(
            TodoFunctions.fetch_todo_list_by_id,
            target_value,
        )
        if not todo_list:
            raise ValidationError(
                "Please select a valid list from autocomplete.",
                ephemeral=True,
            )

        await self._validate_list_access(interaction, todo_list)
        scope_value = TodoFunctions._normalize_scope(str(todo_list.get("scope") or ""))
        return todo_list, scope_value, False

    async def _build_list_target_autocomplete_options(
        self,
        interaction: discord.Interaction,
        current: str,
        *,
        include_all_server: bool = False,
        custom_only: bool = False,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        options: List[app_commands.Choice[str]] = []

        if not custom_only:
            base_options = [
                app_commands.Choice(name="This Channel", value="channel"),
                app_commands.Choice(name="Personal", value="personal"),
            ]
            if interaction.guild is not None and include_all_server:
                base_options.insert(
                    1,
                    app_commands.Choice(
                        name="All Server Channels",
                        value="all_server",
                    ),
                )

            options.extend(
                option
                for option in base_options
                if not query or query in option.name.lower()
            )

        try:
            custom_lists = await asyncio.to_thread(
                TodoFunctions.list_custom_lists_for_context,
                interaction.guild_id,
                interaction.user.id,
                interaction.channel_id,
                25,
            )
        except Exception:
            custom_lists = []

        for todo_list in custom_lists:
            raw_id = todo_list.get("_id")
            if raw_id is None:
                continue
            label = self._custom_list_option_label(todo_list)
            if query and query not in label.lower():
                continue
            options.append(
                app_commands.Choice(
                    name=label,
                    value=str(raw_id),
                )
            )
            if len(options) >= 25:
                return options[:25]

        if custom_only or interaction.guild is None:
            return options[:25]

        for channel in interaction.guild.text_channels:
            channel_name = getattr(channel, "name", None)
            channel_id = getattr(channel, "id", None)
            if channel_name is None or channel_id is None:
                continue
            if query and query not in channel_name.lower():
                continue
            options.append(
                app_commands.Choice(
                    name=f"#{channel_name}"[:100],
                    value=f"channel:{channel_id}",
                )
            )
            if len(options) >= 25:
                break

        return options[:25]

    @list_group.command(name="show", description="Show all items on a list")
    @app_commands.rename(list_target="list")
    @app_commands.describe(
        sort="Sort order for items",
        status="Filter by item status",
        list_target="Which list to show",
        assignee="Filter by assignee (None = unassigned, Me = yourself)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        sort=_SORT_CHOICES,
        status=_LIST_STATUS_FILTER_CHOICES,
        visibility=VISIBILITY_CHOICES,
    )
    async def list_view(
        self,
        interaction: discord.Interaction,
        sort: Optional[app_commands.Choice[str]] = None,
        status: Optional[app_commands.Choice[str]] = None,
        list_target: Optional[str] = None,
        assignee: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        todo_list, scope_value, use_all_server_channels = await self._resolve_list_target(
            interaction,
            list_target,
            allow_all_server=True,
        )

        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
            dm_default_visibility="public",
        )
        sort_value = sort.value if sort else "ascending"
        status_value = status.value if status else "all"
        assignee_filter_user_id: Optional[int] = None
        assignee_filter_unassigned = False
        assignee_value = (assignee or "").strip()
        if assignee_value:
            if assignee_value == "__none__":
                assignee_filter_unassigned = True
            else:
                try:
                    assignee_filter_user_id = TodoFunctions.parse_assignee_token(
                        assignee_value,
                        interaction.user.id,
                    )
                except ValueError as exc:
                    raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        await interaction.response.defer(ephemeral=ephemeral)

        try:
            if use_all_server_channels:
                todo_list = {
                    "name": "All Server Channels",
                    "scope": "channel",
                    "guild_id": interaction.guild_id,
                }
                items = await asyncio.to_thread(
                    TodoFunctions.list_items_on_guild,
                    interaction.guild_id,
                    sort_value,
                )
            else:
                if todo_list is None:
                    raise ValueError("That list was not found.")
                items = await asyncio.to_thread(
                    TodoFunctions.list_items_on_list,
                    todo_list["_id"],
                    sort_value,
                )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while loading that list.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not items:
            payload = TodoEmbeds.list_items_embed(
                todo_list,
                items,
                sort_value,
                status_value,
            )
            await interaction.followup.send(ephemeral=ephemeral, **payload)
            return

        view = TodoListItemsView(
            todo_list=todo_list,
            items=items,
            sort=sort_value,
            status_filter=status_value,
            assignee_filter_id=assignee_filter_user_id,
            assignee_filter_unassigned=assignee_filter_unassigned,
            user_id=interaction.user.id,
            view_scope="all_server" if use_all_server_channels else "list",
            guild_id=interaction.guild_id,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            view=view,
            **view.payload(),
        )

    @list_view.autocomplete("list_target")
    async def list_view_target_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._build_list_target_autocomplete_options(
            interaction,
            current,
            include_all_server=True,
        )

    @list_view.autocomplete("assignee")
    async def list_view_assignee_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self.todo_assign_autocomplete(interaction, current)

    @list_group.command(name="clear", description="Remove all the items from a list")
    @app_commands.rename(list_target="list")
    @app_commands.describe(
        list_target="Which list to clear",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def list_clear(
        self,
        interaction: discord.Interaction,
        list_target: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        todo_list, scope_value, use_all_server_channels = await self._resolve_list_target(
            interaction,
            list_target,
            allow_all_server=True,
        )

        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        try:
            if use_all_server_channels:
                list_name = "All Server Channels"
                deleted_count = await asyncio.to_thread(
                    TodoFunctions.clear_items_on_guild,
                    interaction.guild_id,
                )
            else:
                if todo_list is None:
                    raise ValueError("That list was not found.")
                list_name = str(todo_list.get("name") or "List")
                deleted_count = await asyncio.to_thread(
                    TodoFunctions.clear_todo_list_items,
                    todo_list["_id"],
                )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while clearing that list.",
                ephemeral=ephemeral,
                cause=exc,
            )

        result_view = TodoListDescriptionView(
            title="Todo List Cleared",
            description=(
                f"List: `{list_name}`\nRemoved items: `{deleted_count}`"
                if not use_all_server_channels
                else f"List: `All Server Channels`\nRemoved items: `{deleted_count}`"
            ),
            color=discord.Colour.orange(),
            todo_list=None if use_all_server_channels else todo_list,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **result_view.response_payload(),
        )

    @list_clear.autocomplete("list_target")
    async def list_clear_target_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._build_list_target_autocomplete_options(
            interaction,
            current,
            include_all_server=True,
        )

    @list_group.command(name="all", description="Show all available todo lists")
    @app_commands.describe(
        scope="Which lists to include",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        scope=_LIST_DIRECTORY_SCOPE_CHOICES,
        visibility=VISIBILITY_CHOICES,
    )
    async def list_all(
        self,
        interaction: discord.Interaction,
        scope: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = (
            scope.value
            if scope
            else ("server" if interaction.guild_id is not None else "personal")
        )
        if interaction.guild_id is None:
            scope_value = "personal"
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            "channel" if interaction.guild_id is not None else "personal",
            visibility,
            dm_default_visibility="public",
        )
        await interaction.response.defer(ephemeral=ephemeral)

        server_lists: List[Dict[str, Any]] = []
        personal_lists: List[Dict[str, Any]] = []

        try:
            if interaction.guild_id is not None and scope_value == "server":
                channel_list = await asyncio.to_thread(
                    TodoFunctions.get_or_create_implicit_list,
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                    getattr(interaction.channel, "name", None),
                    "channel",
                )
                server_lists.append(
                    {
                        "label": "Built-in",
                        "name": str(channel_list.get("name") or "This Channel"),
                        "item_count": await asyncio.to_thread(
                            TodoFunctions.count_items_on_list,
                            channel_list.get("_id"),
                        ),
                    }
                )

                custom_server_lists = await asyncio.to_thread(
                    TodoFunctions.list_custom_lists_for_scope,
                    interaction.guild_id,
                    interaction.user.id,
                    interaction.channel_id,
                    "channel",
                    100,
                )
                for todo_list in custom_server_lists:
                    server_lists.append(
                        {
                            "label": "Custom",
                            "name": str(todo_list.get("name") or "Unnamed"),
                            "item_count": await asyncio.to_thread(
                                TodoFunctions.count_items_on_list,
                                todo_list.get("_id"),
                            ),
                        }
                    )

            if scope_value == "personal":
                personal_list = await asyncio.to_thread(
                    TodoFunctions.get_or_create_implicit_list,
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                    getattr(interaction.channel, "name", None),
                    "personal",
                )
                personal_lists.append(
                    {
                        "label": "Built-in",
                        "name": str(personal_list.get("name") or "Personal"),
                        "item_count": await asyncio.to_thread(
                            TodoFunctions.count_items_on_list,
                            personal_list.get("_id"),
                        ),
                    }
                )

                custom_personal_lists = await asyncio.to_thread(
                    TodoFunctions.list_custom_lists_for_scope,
                    interaction.guild_id,
                    interaction.user.id,
                    interaction.channel_id,
                    "personal",
                    100,
                )
                for todo_list in custom_personal_lists:
                    personal_lists.append(
                        {
                            "label": "Custom",
                            "name": str(todo_list.get("name") or "Unnamed"),
                            "item_count": await asyncio.to_thread(
                                TodoFunctions.count_items_on_list,
                                todo_list.get("_id"),
                            ),
                        }
                    )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while loading available lists.",
                ephemeral=ephemeral,
                cause=exc,
            )

        payload = TodoEmbeds.list_directory_embed(server_lists, personal_lists)
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @list_group.command(name="create", description="Create a new custom todo list")
    @app_commands.describe(
        name="Name of the new list",
        scope="Where this list should live",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        scope=_LIST_SCOPE_CHOICES,
        visibility=VISIBILITY_CHOICES,
    )
    async def list_create(
        self,
        interaction: discord.Interaction,
        name: str,
        scope: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        selected_scope = (
            scope.value if scope else ("server" if interaction.guild_id is not None else "personal")
        )
        scope_value = "personal" if selected_scope == "personal" else "channel"
        if interaction.guild_id is None:
            scope_value = "personal"

        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.create_todo_list,
                interaction.guild_id,
                interaction.user.id,
                None,
                name,
                scope_value,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while creating that list.",
                ephemeral=ephemeral,
                cause=exc,
            )

        result_view = TodoListDescriptionView(
            title="Todo List Created",
            description=(
                f"List: `{todo_list.get('name') or 'List'}`\n"
                f"Items: `0`"
            ),
            color=discord.Colour.green(),
            todo_list=todo_list,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **result_view.response_payload(),
        )

    @list_group.command(name="edit", description="Edit a custom todo list name")
    @app_commands.rename(list_target="list")
    @app_commands.describe(
        list_target="Which custom list to rename",
        name="New list name",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def list_rename(
        self,
        interaction: discord.Interaction,
        list_target: str,
        name: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        todo_list, scope_value, use_all_server_channels = await self._resolve_list_target(
            interaction,
            list_target,
            allow_all_server=False,
        )
        if use_all_server_channels or todo_list is None:
            raise ValidationError(
                "Please select a custom list from autocomplete.",
                ephemeral=True,
            )
        if TodoFunctions.list_type(todo_list) != TodoFunctions._CUSTOM_LIST_TYPE:
            raise ValidationError(
                "Only custom lists can be renamed.",
                ephemeral=True,
            )

        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        old_name = str(todo_list.get("name") or "List")
        try:
            updated_list = await asyncio.to_thread(
                TodoFunctions.rename_todo_list,
                todo_list.get("_id"),
                name,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while renaming that list.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not updated_list:
            raise UserVisibleError(
                "That list could not be renamed.",
                ephemeral=ephemeral,
            )

        result_view = TodoListDescriptionView(
            title="Todo List Updated",
            description=(
                f"Previous name: `{old_name}`\n"
                f"New name: `{updated_list.get('name') or 'List'}`"
            ),
            color=discord.Colour.blurple(),
            todo_list=updated_list,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **result_view.response_payload(),
        )

    @list_rename.autocomplete("list_target")
    async def list_rename_target_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._build_list_target_autocomplete_options(
            interaction,
            current,
            custom_only=True,
        )

    @list_group.command(name="delete", description="Delete a custom todo list")
    @app_commands.rename(list_target="list")
    @app_commands.describe(
        list_target="Which custom list to delete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        visibility=VISIBILITY_CHOICES,
    )
    async def list_delete(
        self,
        interaction: discord.Interaction,
        list_target: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        todo_list, scope_value, use_all_server_channels = await self._resolve_list_target(
            interaction,
            list_target,
            allow_all_server=False,
        )
        if use_all_server_channels or todo_list is None:
            raise ValidationError(
                "Please select a custom list from autocomplete.",
                ephemeral=True,
            )
        if TodoFunctions.list_type(todo_list) != TodoFunctions._CUSTOM_LIST_TYPE:
            raise ValidationError(
                "Only custom lists can be deleted.",
                ephemeral=True,
            )

        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        list_name = str(todo_list.get("name") or "List")
        try:
            deleted, deleted_count = await asyncio.to_thread(
                TodoFunctions.delete_todo_list,
                todo_list.get("_id"),
            )
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while deleting that list.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not deleted:
            raise UserVisibleError(
                "That list could not be deleted.",
                ephemeral=ephemeral,
            )

        result_view = TodoListDescriptionView(
            title="Todo List Deleted",
            description=(
                f"List: `{list_name}`\n"
                f"Removed items: `{deleted_count}`"
            ),
            color=discord.Colour.red(),
            todo_list=None,
            user_id=interaction.user.id,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **result_view.response_payload(),
        )

    @list_delete.autocomplete("list_target")
    async def list_delete_target_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._build_list_target_autocomplete_options(
            interaction,
            current,
            custom_only=True,
        )

    @todo_group.command(name="add", description="Add an item to a list")
    @app_commands.describe(
        text="Item text",
        description="Additional details (optional)",
        due="Due date/time (natural language, same as /reminder)",
        list="Where to add this item",
        status="Initial progress status",
        assignee="Who should be assigned (optional)",
        notify_assignee="Mention the assignee with the todo embed",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        status=_ITEM_STATUS_CHOICES,
        notify_assignee=_YES_NO_CHOICES,
        visibility=VISIBILITY_CHOICES,
    )
    async def item_add(
        self,
        interaction: discord.Interaction,
        text: str,
        description: Optional[str] = None,
        due: Optional[str] = None,
        list: Optional[str] = None,
        status: Optional[app_commands.Choice[str]] = None,
        assignee: Optional[str] = None,
        notify_assignee: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        todo_list, scope_value, use_all_server_channels = await self._resolve_list_target(
            interaction,
            list,
            allow_all_server=False,
        )
        if use_all_server_channels or todo_list is None:
            raise ValidationError(
                "Please select a valid list from autocomplete.",
                ephemeral=True,
            )

        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        status_value = status.value if status else "todo"
        notify_enabled = (notify_assignee.value if notify_assignee else "yes") == "yes"
        locale_code = str(getattr(interaction, "locale", "") or "").strip() or None
        timezone = None
        if (due or "").strip():

            async def _continue_with_timezone(
                followup_interaction: discord.Interaction,
                resolved_timezone: str,
            ) -> None:
                await self._run_item_add(
                    interaction=followup_interaction,
                    text=text,
                    description=description,
                    due=due,
                    todo_list=todo_list,
                    status_value=status_value,
                    assignee=assignee,
                    notify_enabled=notify_enabled,
                    ephemeral=ephemeral,
                    timezone=resolved_timezone,
                    locale_code=locale_code,
                )

            timezone = await ensure_user_timezone(
                interaction,
                _continue_with_timezone,
                continue_message="Timezone saved as `{timezone}`. Continuing `/todo add`.",
            )
            if timezone is None:
                return

        await interaction.response.defer(ephemeral=ephemeral)
        await self._run_item_add(
            interaction=interaction,
            text=text,
            description=description,
            due=due,
            todo_list=todo_list,
            status_value=status_value,
            assignee=assignee,
            notify_enabled=notify_enabled,
            ephemeral=ephemeral,
            timezone=timezone,
            locale_code=locale_code,
        )

    async def _run_item_add(
        self,
        interaction: discord.Interaction,
        text: str,
        description: Optional[str],
        due: Optional[str],
        todo_list: Dict[str, Any],
        status_value: str,
        assignee: Optional[str],
        notify_enabled: bool,
        ephemeral: bool,
        timezone: Optional[str],
        locale_code: Optional[str],
    ) -> None:
        try:
            assignee_id = TodoFunctions.parse_assignee_token(
                assignee,
                interaction.user.id,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

        description_value = description.strip() if description else ""
        item_text = text
        if description_value:
            item_text = f"{text}\n{description_value}"

        try:
            current_list = await asyncio.to_thread(
                TodoFunctions.fetch_todo_list_by_id,
                todo_list.get("_id"),
            )
            if current_list is None:
                raise ValueError("That list no longer exists.")
            todo_list = current_list
            item, due_dt = await asyncio.to_thread(
                TodoFunctions.add_item_to_list,
                todo_list,
                interaction.user.id,
                item_text,
                due,
                status_value,
                assignee_id,
                timezone,
                locale_code,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while adding that item.",
                ephemeral=ephemeral,
                cause=exc,
            )

        reminder_failed = False
        if due_dt:
            try:
                await asyncio.to_thread(
                    TodoFunctions.insert_todo_task,
                    item,
                    due_dt,
                )
            except Exception:
                reminder_failed = True

        payload = TodoEmbeds.item_details_embed(todo_list, item)
        await interaction.followup.send(ephemeral=ephemeral, **payload)

        if reminder_failed:
            await interaction.followup.send(
                ephemeral=True,
                content="Item was added, but reminder scheduling failed.",
            )

        notify_failed = False
        target_scope = TodoFunctions._normalize_scope(str(todo_list.get("scope") or ""))
        if (
            notify_enabled
            and assignee_id is not None
            and target_scope == "channel"
            and interaction.guild_id is not None
        ):
            notify_payload = TodoEmbeds.item_details_embed(todo_list, item)
            try:
                channel = None
                target_channel_id = todo_list.get("channel_id")
                if (
                    target_channel_id is not None
                    and interaction.guild is not None
                ):
                    channel = interaction.guild.get_channel(target_channel_id)
                if channel is None:
                    channel = interaction.channel
                if channel is not None:
                    await channel.send(content=f"<@{assignee_id}>", **notify_payload)
                else:
                    notify_failed = True
            except Exception:
                notify_failed = True

        if notify_failed:
            await interaction.followup.send(
                ephemeral=True,
                content="Assignee notification failed.",
            )

    @item_add.autocomplete("assignee")
    async def todo_add_assignee_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self.todo_assign_autocomplete(interaction, current)

    @item_add.autocomplete("list")
    async def todo_add_list_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        return await self._build_list_target_autocomplete_options(
            interaction,
            current,
            include_all_server=False,
        )

    @todo_group.command(name="show", description="Show the text of an item")
    @app_commands.describe(
        todo="Todo from autocomplete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def item_view(
        self,
        interaction: discord.Interaction,
        todo: int,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                "channel" if interaction.guild_id is not None else "personal",
            )
            item = await asyncio.to_thread(
                TodoFunctions.fetch_item_on_list_or_error,
                todo_list["_id"],
                todo,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while loading that item.",
                ephemeral=ephemeral,
                cause=exc,
            )

        payload = TodoEmbeds.item_details_embed(todo_list, item)
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @todo_group.command(name="edit", description="Edit the text of an existing item")
    @app_commands.describe(
        todo="Todo from autocomplete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def item_edit(
        self,
        interaction: discord.Interaction,
        todo: int,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                "channel" if interaction.guild_id is not None else "personal",
            )
            items = await asyncio.to_thread(
                TodoFunctions.list_items_on_list,
                todo_list["_id"],
                "ascending",
            )
            item = await asyncio.to_thread(
                TodoFunctions.fetch_item_on_list_or_error,
                todo_list["_id"],
                todo,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while loading that item.",
                ephemeral=ephemeral,
                cause=exc,
            )

        parent_view = TodoListItemsView(
            todo_list=todo_list,
            items=items,
            sort="ascending",
            status_filter="all",
            user_id=interaction.user.id,
            view_scope="list",
            guild_id=interaction.guild_id,
        )
        assignee_options = parent_view._build_assignee_select_options(
            interaction,
            item,
        )
        list_options = []
        try:
            list_docs = await asyncio.to_thread(
                TodoFunctions.list_candidate_lists_for_item_scope,
                item,
                interaction.user.id,
                25,
            )
            list_options = parent_view._build_list_select_options(item, list_docs)
        except Exception:
            list_options = []

        modal_locale = str(getattr(interaction, "locale", "") or "").strip() or None
        try:
            modal_timezone = await asyncio.to_thread(
                UserSettingsFunctions.get_timezone,
                interaction.user.id,
            )
        except Exception:
            modal_timezone = None

        try:
            await interaction.response.send_modal(
                TodoItemEditModal(
                    parent_view=parent_view,
                    item=item,
                    item_number=todo,
                    source_message=None,
                    assignee_options=assignee_options,
                    list_options=list_options,
                    return_item_embed=True,
                    locale_code=modal_locale,
                    timezone=modal_timezone,
                )
            )
        except discord.HTTPException as exc:
            if exc.code == 50035 and "must be one of (4,)" in str(exc):
                await interaction.response.send_modal(
                    TodoItemEditModal(
                        parent_view=parent_view,
                        item=item,
                        item_number=todo,
                        source_message=None,
                        return_item_embed=True,
                        locale_code=modal_locale,
                        timezone=modal_timezone,
                    )
                )
                return

            raise UserVisibleError(
                "Something went wrong while opening the edit dialog.",
                ephemeral=ephemeral,
                cause=exc,
            )

    @todo_group.command(name="status", description="Set the progress of an item")
    @app_commands.describe(
        todo="Todo from autocomplete",
        status="New progress status",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(
        status=_ITEM_STATUS_CHOICES,
        visibility=VISIBILITY_CHOICES,
    )
    async def item_status(
        self,
        interaction: discord.Interaction,
        todo: int,
        status: app_commands.Choice[str],
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                "channel" if interaction.guild_id is not None else "personal",
            )
            item = await asyncio.to_thread(
                TodoFunctions.fetch_item_on_list_or_error,
                todo_list["_id"],
                todo,
            )
            updated_item = await asyncio.to_thread(
                TodoFunctions.set_item_status,
                item["_id"],
                status.value,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while updating that status.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not updated_item:
            raise UserVisibleError(
                "That item could not be updated.",
                ephemeral=ephemeral,
            )

        payload = TodoEmbeds.item_details_embed(todo_list, updated_item)
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @todo_group.command(name="delete", description="Delete an item from a list")
    @app_commands.describe(
        todo="Todo from autocomplete",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def item_delete(
        self,
        interaction: discord.Interaction,
        todo: int,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                "channel" if interaction.guild_id is not None else "personal",
            )
            item = await asyncio.to_thread(
                TodoFunctions.fetch_item_on_list_or_error,
                todo_list["_id"],
                todo,
            )
            deleted = await asyncio.to_thread(TodoFunctions.delete_item, item["_id"])
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while deleting that item.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not deleted:
            raise UserVisibleError(
                "That item could not be deleted.",
                ephemeral=ephemeral,
            )

        deleted_payload = TodoEmbeds.deleted_item_embed(
            str(todo_list.get("name") or "List"),
            TodoFunctions.task_name_from_item(item),
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            **deleted_payload,
        )

    @todo_group.command(name="assign", description="Assign or unassign an item")
    @app_commands.describe(
        todo="Todo from autocomplete",
        assignee="Who should be assigned (None = unassign, Me = yourself)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def todo_assign(
        self,
        interaction: discord.Interaction,
        todo: int,
        assignee: str,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        scope_value = "channel" if interaction.guild_id is not None else "personal"
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        await interaction.response.defer(ephemeral=ephemeral)

        try:
            assignee_id = TodoFunctions.parse_assignee_token(
                assignee,
                interaction.user.id,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                "channel" if interaction.guild_id is not None else "personal",
            )
            item = await asyncio.to_thread(
                TodoFunctions.fetch_item_on_list_or_error,
                todo_list["_id"],
                todo,
            )
            updated_item = await asyncio.to_thread(
                TodoFunctions.set_item_assignee,
                item["_id"],
                assignee_id,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while updating assignment.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not updated_item:
            raise UserVisibleError(
                "That item could not be updated.",
                ephemeral=ephemeral,
            )

        payload = TodoEmbeds.item_details_embed(todo_list, updated_item)
        await interaction.followup.send(ephemeral=ephemeral, **payload)

    @todo_assign.autocomplete("assignee")
    async def todo_assign_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        options: List[app_commands.Choice[str]] = [
            app_commands.Choice(name="None", value="__none__"),
            app_commands.Choice(name="Me", value="__me__"),
        ]

        guild = interaction.guild
        if guild is None:
            return options

        members = getattr(interaction.channel, "members", None) or guild.members
        seen_ids = {interaction.user.id}
        for member in members:
            if member.bot:
                continue
            if member.id in seen_ids:
                continue
            if query:
                haystack = f"{member.display_name} {member.name} {member.id}".lower()
                if query not in haystack:
                    continue

            seen_ids.add(member.id)
            label = f"{member.display_name} (@{member.name})"
            options.append(
                app_commands.Choice(
                    name=label[:100],
                    value=f"user:{member.id}",
                )
            )
            if len(options) >= 25:
                break

        return options[:25]

    async def todo_item_number_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        query = (current or "").strip().lower()
        scope_value = "channel" if interaction.guild_id is not None else "personal"

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                scope_value,
            )
            items = await asyncio.to_thread(
                TodoFunctions.list_items_on_list,
                todo_list["_id"],
                "ascending",
            )
        except Exception:
            return []

        options: List[app_commands.Choice[int]] = []
        for item in items:
            item_no = item.get("item_no")
            if not isinstance(item_no, int):
                continue

            todo_name = str(item.get("name") or "").strip() or "Untitled"
            status = TodoFunctions.status_label(TodoFunctions.item_status(item))
            due_value = item.get("due")
            due_label = (
                DueDateService.format_due(due_value) if due_value else "No due date"
            )
            search_text = f"{todo_name} {status} {due_label}".lower()
            if query and query not in search_text:
                continue

            label = f"{todo_name} [{status}] - {due_label}"
            options.append(
                app_commands.Choice(
                    name=label[:100],
                    value=item_no,
                )
            )
            if len(options) >= 25:
                break

        return options[:25]

    @item_view.autocomplete("todo")
    async def todo_item_view_number_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        return await self.todo_item_number_autocomplete(interaction, current)

    @item_edit.autocomplete("todo")
    async def todo_item_edit_number_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        return await self.todo_item_number_autocomplete(interaction, current)

    @item_status.autocomplete("todo")
    async def todo_item_status_number_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        return await self.todo_item_number_autocomplete(interaction, current)

    @item_delete.autocomplete("todo")
    async def todo_item_delete_number_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        return await self.todo_item_number_autocomplete(interaction, current)

    @todo_assign.autocomplete("todo")
    async def todo_item_assign_number_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[int]]:
        return await self.todo_item_number_autocomplete(interaction, current)


async def setup(client: commands.Bot) -> None:
    await client.add_cog(TodoCog(client))
    client.tree.add_command(add_message_to_todo)
    client.tree.add_command(add_message_to_personal_todo)
