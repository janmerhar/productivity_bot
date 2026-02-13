import asyncio
from typing import Optional, List

import discord
from discord import app_commands
from discord.ext import commands

from classes.TodoFunctions import TodoFunctions
from embeds.TodoEmbeds import TodoEmbeds, TodoListItemsView
from services.discord_helpers import resolve_ephemeral_from_scope
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import VISIBILITY_CHOICES, VISIBILITY_DESC


_SORT_CHOICES = [
    app_commands.Choice(name="Ascending", value="ascending"),
    app_commands.Choice(name="Descending", value="descending"),
]
_ADD_LIST_CHOICES = [
    app_commands.Choice(name="This Channel", value="channel"),
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

    payload = TodoEmbeds.insert_todo_embed(
        name=document["name"],
        description=document.get("description"),
        due=None,
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

    payload = TodoEmbeds.insert_todo_embed(
        name=document["name"],
        description=document.get("description"),
        due=None,
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

    @list_group.command(name="view", description="Show all items on a list")
    @app_commands.describe(
        sort="Sort order for items",
        status="Filter by item status",
        list="Which todo scope to show",
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
        list: Optional[str] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        target_value = (list or "").strip()
        selected_channel_id: Optional[int] = None
        selected_channel_name: Optional[str] = None
        use_all_server_channels = False
        if not target_value:
            target_value = "channel" if interaction.guild_id is not None else "personal"

        if interaction.guild_id is None:
            target_value = "personal"

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
            selected_channel_name = getattr(selected_channel, "name", None)
            target_value = "channel"
        elif target_value == "all_server":
            if interaction.guild_id is None:
                raise ValidationError(
                    "All server channels is only available in servers.",
                    ephemeral=True,
                )
            target_value = "channel"
            use_all_server_channels = True
        elif target_value not in {"channel", "personal"}:
            raise ValidationError(
                "Please select a valid list target from autocomplete.",
                ephemeral=True,
            )

        scope_value = "personal" if target_value == "personal" else "channel"
        ephemeral = resolve_ephemeral_from_scope(
            interaction.guild_id,
            scope_value,
            visibility,
        )
        sort_value = sort.value if sort else "ascending"
        status_value = status.value if status else "all"
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
            elif target_value == "personal":
                todo_list = await asyncio.to_thread(
                    TodoFunctions.get_or_create_implicit_list,
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                    getattr(interaction.channel, "name", None),
                    "personal",
                )
                items = await asyncio.to_thread(
                    TodoFunctions.list_items_on_list,
                    todo_list["_id"],
                    sort_value,
                )
            elif selected_channel_id is not None:
                todo_list = await asyncio.to_thread(
                    TodoFunctions.get_or_create_channel_list,
                    interaction.guild_id,
                    selected_channel_id,
                    interaction.user.id,
                    selected_channel_name,
                )
                items = await asyncio.to_thread(
                    TodoFunctions.list_items_on_list,
                    todo_list["_id"],
                    sort_value,
                )
            else:
                todo_list = await asyncio.to_thread(
                    TodoFunctions.get_or_create_implicit_list,
                    interaction.guild_id,
                    interaction.channel_id,
                    interaction.user.id,
                    getattr(interaction.channel, "name", None),
                    "channel",
                )
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
            user_id=interaction.user.id,
            view_scope="all_server" if use_all_server_channels else "list",
            guild_id=interaction.guild_id,
        )
        await interaction.followup.send(
            ephemeral=ephemeral,
            view=view,
            **view.payload(),
        )

    @list_view.autocomplete("list")
    async def list_view_list_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        guild = interaction.guild
        base_options = [
            app_commands.Choice(name="This Channel", value="channel"),
            app_commands.Choice(name="Personal", value="personal"),
        ]
        if guild is not None:
            base_options.insert(
                1,
                app_commands.Choice(name="All Server Channels", value="all_server"),
            )
        options: List[app_commands.Choice[str]] = [
            option for option in base_options if not query or query in option.name.lower()
        ]

        if guild is None:
            return options[:25]

        for channel in guild.channels:
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

    @list_group.command(name="clear", description="Remove all the items from a list")
    @app_commands.describe(
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def list_clear(
        self,
        interaction: discord.Interaction,
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

        await interaction.followup.send(
            ephemeral=ephemeral,
            content=f"Cleared `{todo_list.get('name')}` ({deleted_count} items removed).",
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
        list=_ADD_LIST_CHOICES,
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
        list: Optional[app_commands.Choice[str]] = None,
        status: Optional[app_commands.Choice[str]] = None,
        assignee: Optional[str] = None,
        notify_assignee: Optional[app_commands.Choice[str]] = None,
        visibility: Optional[app_commands.Choice[str]] = None,
    ) -> None:
        target_value = (
            list.value
            if list
            else ("channel" if interaction.guild_id is not None else "personal")
        )
        if interaction.guild_id is None:
            target_value = "personal"

        scope_value = target_value
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

        status_value = status.value if status else "todo"
        notify_enabled = (notify_assignee.value if notify_assignee else "yes") == "yes"
        description_value = description.strip() if description else ""
        item_text = text
        if description_value:
            item_text = f"{text}\n{description_value}"

        try:
            todo_list = await asyncio.to_thread(
                TodoFunctions.get_or_create_implicit_list,
                interaction.guild_id,
                interaction.channel_id,
                interaction.user.id,
                getattr(interaction.channel, "name", None),
                target_value,
            )
            item, due_dt = await asyncio.to_thread(
                TodoFunctions.add_item_to_list,
                todo_list,
                interaction.user.id,
                item_text,
                due,
                status_value,
                assignee_id,
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

        message = (
            f"Added item #{item.get('item_no')} to `{todo_list.get('name')}` "
            f"(due: {TodoFunctions.format_due(due_dt)})."
        )
        message += f" Status: {TodoFunctions.status_label(status_value)}."
        if assignee_id is not None:
            message += f" Assignee: <@{assignee_id}>."
        if reminder_failed:
            message += " Reminder scheduling failed."

        await interaction.followup.send(ephemeral=ephemeral, content=message)

        notify_failed = False
        if notify_enabled and assignee_id is not None and interaction.guild_id is not None:
            notify_payload = TodoEmbeds.item_details_embed(todo_list, item)
            try:
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

    @todo_group.command(name="view", description="Show the text of an item")
    @app_commands.describe(
        item_number="Item number from /todo list view",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def item_view(
        self,
        interaction: discord.Interaction,
        item_number: int,
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
                item_number,
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
        item_number="Item number from /todo list view",
        text="New item text",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def item_edit(
        self,
        interaction: discord.Interaction,
        item_number: int,
        text: str,
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
                item_number,
            )
            updated = await asyncio.to_thread(
                TodoFunctions.set_item_text,
                item["_id"],
                text,
            )
        except ValueError as exc:
            raise ValidationError(str(exc), ephemeral=ephemeral, cause=exc)
        except Exception as exc:
            raise UserVisibleError(
                "Something went wrong while editing that item.",
                ephemeral=ephemeral,
                cause=exc,
            )

        if not updated:
            raise UserVisibleError(
                "That item could not be updated.",
                ephemeral=ephemeral,
            )

        await interaction.followup.send(
            ephemeral=ephemeral,
            content=f"Updated item #{item_number} on `{todo_list.get('name')}`.",
        )

    @todo_group.command(name="status", description="Set the progress of an item")
    @app_commands.describe(
        item_number="Item number from /todo list view",
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
        item_number: int,
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
                item_number,
            )
            updated = await asyncio.to_thread(
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

        if not updated:
            raise UserVisibleError(
                "That item could not be updated.",
                ephemeral=ephemeral,
            )

        await interaction.followup.send(
            ephemeral=ephemeral,
            content=(
                f"Updated item #{item_number} on `{todo_list.get('name')}` "
                f"to {TodoFunctions.status_label(status.value)}."
            ),
        )

    @todo_group.command(name="delete", description="Delete an item from a list")
    @app_commands.describe(
        item_number="Item number from /todo list view",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def item_delete(
        self,
        interaction: discord.Interaction,
        item_number: int,
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
                item_number,
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

        await interaction.followup.send(
            ephemeral=ephemeral,
            content=f"Deleted item #{item_number} from `{todo_list.get('name')}`.",
        )

    @todo_group.command(name="assign", description="Assign or unassign an item")
    @app_commands.describe(
        item_number="Item number from /todo list view",
        assignee="Who should be assigned (None = unassign, Me = yourself)",
        visibility=VISIBILITY_DESC,
    )
    @app_commands.choices(visibility=VISIBILITY_CHOICES)
    async def todo_assign(
        self,
        interaction: discord.Interaction,
        item_number: int,
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
                item_number,
            )
            updated = await asyncio.to_thread(
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

        if not updated:
            raise UserVisibleError(
                "That item could not be updated.",
                ephemeral=ephemeral,
            )

        if assignee_id is None:
            message = (
                f"Unassigned item #{item_number} on `{todo_list.get('name')}`."
            )
        else:
            message = (
                f"Assigned <@{assignee_id}> to item #{item_number} "
                f"on `{todo_list.get('name')}`."
            )

        await interaction.followup.send(ephemeral=ephemeral, content=message)

    @todo_assign.autocomplete("assignee")
    async def todo_assign_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        query = (current or "").strip().lower()
        options: List[app_commands.Choice[str]] = [
            app_commands.Choice(name="None (Unassign)", value="__none__"),
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


async def setup(client: commands.Bot) -> None:
    await client.add_cog(TodoCog(client))
    client.tree.add_command(add_message_to_todo)
    client.tree.add_command(add_message_to_personal_todo)


