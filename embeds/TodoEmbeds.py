import asyncio
import datetime
import math
from typing import Optional, Union, List, Dict, Any

import discord

from classes.TodoFunctions import TodoFunctions
from services.error_reporting import UserVisibleError, ValidationError, handle_interaction_error

_MODAL_SELECTS_SUPPORTED = True


class TodoListView(discord.ui.View):
    def __init__(
        self,
        todos: List[Dict[str, Any]],
        mode: str,
        sort: str,
        user_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> None:
        super().__init__(timeout=300)
        self.todos = todos
        self.mode = mode
        self.sort = sort
        self.user_id = user_id
        self.page_size = max(1, page_size)
        self.total_pages = max(1, math.ceil(len(todos) / self.page_size))
        self.page = max(1, min(page, self.total_pages))
        self._build()

    def _page_slice(self) -> List[Dict[str, Any]]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.todos[start:end]

    def _build(self) -> None:
        self.clear_items()

        start_index = (self.page - 1) * self.page_size
        page_items = self._page_slice()

        for offset, todo in enumerate(page_items, start=1):
            todo_id = str(todo.get("_id", ""))
            index = start_index + offset
            button = discord.ui.Button(
                label=str(index),
                style=discord.ButtonStyle.secondary,
                custom_id=f"todo_complete:{todo_id}",
                row=0,
            )

            async def _callback(
                interaction: discord.Interaction,
                todo_name: str = str(todo.get("name") or "todo"),
                todo_object_id: str = todo_id,
            ) -> None:
                await interaction.response.defer(ephemeral=True)
                updated = await asyncio.to_thread(
                    TodoFunctions.complete_todo,
                    todo_object_id,
                    interaction.guild_id,
                    interaction.user.id,
                )
                if not updated:
                    await interaction.followup.send(
                        ephemeral=True,
                        content=f"Couldn't complete '{todo_name}'.",
                    )
                    return
                await interaction.followup.send(
                    ephemeral=True,
                    content=f"Marked '{todo_name}' as done.",
                )

            button.callback = _callback
            self.add_item(button)

        prev_button = discord.ui.Button(
            label="Prev",
            style=discord.ButtonStyle.secondary,
            disabled=self.page <= 1,
            row=1,
        )
        next_button = discord.ui.Button(
            label="Next",
            style=discord.ButtonStyle.secondary,
            disabled=self.page >= self.total_pages,
            row=1,
        )

        async def _prev_callback(interaction: discord.Interaction) -> None:
            if self.page <= 1:
                await interaction.response.defer(ephemeral=True)
                return
            self.page -= 1
            self._build()
            payload = TodoEmbeds.list_todos_embed(
                todos=self.todos,
                mode=self.mode,
                sort=self.sort,
                page=self.page,
                page_size=self.page_size,
            )
            await interaction.response.edit_message(view=self, **payload)

        async def _next_callback(interaction: discord.Interaction) -> None:
            if self.page >= self.total_pages:
                await interaction.response.defer(ephemeral=True)
                return
            self.page += 1
            self._build()
            payload = TodoEmbeds.list_todos_embed(
                todos=self.todos,
                mode=self.mode,
                sort=self.sort,
                page=self.page,
                page_size=self.page_size,
            )
            await interaction.response.edit_message(view=self, **payload)

        prev_button.callback = _prev_callback
        next_button.callback = _next_callback

        self.add_item(prev_button)
        self.add_item(next_button)


class TodoItemEditModal(discord.ui.Modal):
    def __init__(
        self,
        parent_view: "TodoListItemsView",
        item: Dict[str, Any],
        item_number: Any,
        source_message: Optional[discord.Message],
        assignee_options: Optional[List[discord.SelectOption]] = None,
        list_options: Optional[List[discord.SelectOption]] = None,
        return_item_embed: bool = False,
    ) -> None:
        super().__init__(title=f"Edit Item #{item_number}")
        self.parent_view = parent_view
        self.item_id = str(item.get("_id") or "")
        self.item_number = item_number
        self.source_message = source_message
        self.return_item_embed = return_item_embed

        current_task = str(item.get("name") or "").strip() or "Untitled"
        current_text = TodoFunctions.item_text(item)
        current_description = ""
        if current_text:
            prefix = f"{current_task}\n"
            if current_text.startswith(prefix):
                current_description = current_text[len(prefix) :].strip()
            elif current_text.strip().lower() != current_task.lower():
                current_description = current_text.strip()
        if not current_description:
            raw_description = str(item.get("description") or "").strip()
            if raw_description and raw_description.lower() != current_task.lower():
                current_description = raw_description

        current_status = TodoFunctions.item_status(item)
        due_value = item.get("due")
        current_due = "" if not due_value else TodoFunctions.format_due(due_value)
        self.initial_due_raw = str(due_value) if due_value else None
        self.initial_due_display = current_due
        self.current_status = current_status
        self.current_list_id = str(item.get("list_id") or "")
        self.current_list_name = str(
            item.get("list_name")
            or parent_view.todo_list.get("name")
            or ""
        ).strip()
        assignees = item.get("assignees") or []
        current_assignee = f"<@{assignees[0]}>" if assignees else "none"
        self.assignee_select: Optional[discord.ui.Select] = None
        self.list_select: Optional[discord.ui.Select] = None
        self.assignee_input: Optional[discord.ui.TextInput] = None
        self.list_input: Optional[discord.ui.TextInput] = None

        self.task_input = discord.ui.TextInput(
            label="Task text",
            style=discord.TextStyle.short,
            required=True,
            default=current_task[:100],
            max_length=100,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            required=False,
            default=current_description[:800],
            max_length=800,
        )
        self.due_input = discord.ui.TextInput(
            label="Due (optional)",
            placeholder="YYYY-MM-DD HH:MM, ISO, or natural language",
            required=False,
            default=current_due[:100],
            max_length=100,
        )

        self.add_item(self.task_input)
        self.add_item(self.description_input)
        self.add_item(self.due_input)

        if assignee_options and list_options:
            try:
                self.assignee_select = discord.ui.Select(
                    placeholder="Assignee",
                    min_values=1,
                    max_values=1,
                    options=assignee_options[:25],
                    row=3,
                )
                self.list_select = discord.ui.Select(
                    placeholder="List",
                    min_values=1,
                    max_values=1,
                    options=list_options[:25],
                    row=4,
                )
                self.add_item(self.assignee_select)
                self.add_item(self.list_select)
            except Exception:
                self.assignee_select = None
                self.list_select = None
                self.clear_items()
                self.add_item(self.task_input)
                self.add_item(self.description_input)
                self.add_item(self.due_input)

        if self.assignee_select is None or self.list_select is None:
            self.assignee_input = discord.ui.TextInput(
                label="Assignee",
                placeholder="none, me, user:<id>, <@id>, or ID",
                required=True,
                default=current_assignee,
                max_length=64,
            )
            self.list_input = discord.ui.TextInput(
                label="List",
                placeholder="Existing list name or list ID",
                required=True,
                default=self.current_list_name[:80],
                max_length=80,
            )
            self.add_item(self.assignee_input)
            self.add_item(self.list_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not self.item_id:
            await handle_interaction_error(
                interaction,
                ValidationError("That item could not be edited.", ephemeral=True),
            )
            return

        try:
            due_input_value = str(self.due_input.value or "").strip()
            due_value_to_save = due_input_value
            if (
                self.initial_due_raw is not None
                and due_input_value == self.initial_due_display
            ):
                due_value_to_save = self.initial_due_raw

            updated = await asyncio.to_thread(
                TodoFunctions.set_item_fields,
                self.item_id,
                str(self.task_input.value or ""),
                str(self.description_input.value or ""),
                self.current_status,
                due_value_to_save,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(str(exc), ephemeral=True, cause=exc),
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while editing that item.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not updated:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "That item could not be updated.",
                    ephemeral=True,
                ),
            )
            return

        try:
            if self.assignee_select is not None:
                selected_assignee = (
                    self.assignee_select.values[0]
                    if self.assignee_select.values
                    else "__none__"
                )
                assignee_id = TodoFunctions.parse_assignee_token(
                    selected_assignee,
                    interaction.user.id,
                )
            else:
                assignee_value = (
                    str(self.assignee_input.value or "")
                    if self.assignee_input is not None
                    else "none"
                )
                assignee_id = TodoFunctions.parse_assignee_modal_input(
                    assignee_value,
                    interaction.user.id,
                )
            updated_assignee = await asyncio.to_thread(
                TodoFunctions.set_item_assignee,
                self.item_id,
                assignee_id,
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(str(exc), ephemeral=True, cause=exc),
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while updating the assignee.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not updated_assignee:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "That assignee could not be updated.",
                    ephemeral=True,
                ),
            )
            return

        list_token = ""
        list_changed = False
        if self.list_select is not None:
            list_token = self.list_select.values[0] if self.list_select.values else ""
            list_changed = bool(list_token and list_token != self.current_list_id)
        else:
            list_token = (
                str(self.list_input.value or "").strip()
                if self.list_input is not None
                else ""
            )
            list_changed = bool(
                list_token and list_token.lower() != self.current_list_name.lower()
            )

        if list_changed:
            try:
                target_list = await asyncio.to_thread(
                    TodoFunctions.find_list_for_item_scope_by_token,
                    updated_assignee,
                    list_token,
                    interaction.user.id,
                )
                moved = await asyncio.to_thread(
                    TodoFunctions.move_item_to_list,
                    self.item_id,
                    target_list,
                )
            except ValueError as exc:
                await handle_interaction_error(
                    interaction,
                    ValidationError(str(exc), ephemeral=True, cause=exc),
                )
                return
            except Exception as exc:
                await handle_interaction_error(
                    interaction,
                    UserVisibleError(
                        "Something went wrong while moving that item.",
                        ephemeral=True,
                        cause=exc,
                    ),
                )
                return

            if not moved:
                await handle_interaction_error(
                    interaction,
                    UserVisibleError(
                        "That item could not be moved to the selected list.",
                        ephemeral=True,
                    ),
                )
                return

        final_item = updated_assignee
        if list_changed:
            final_item = moved
        if final_item is None:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "That item could not be loaded after update.",
                    ephemeral=True,
                ),
            )
            return

        final_list = self.parent_view.todo_list
        final_list_id = final_item.get("list_id")
        if final_list_id:
            try:
                resolved_list = await asyncio.to_thread(
                    TodoFunctions.fetch_todo_list_by_id,
                    final_list_id,
                )
                if resolved_list is not None:
                    final_list = resolved_list
            except Exception:
                pass

        try:
            await self.parent_view._reload_items()
            self.parent_view._build()
            if self.source_message is not None:
                await self.source_message.edit(
                    view=self.parent_view,
                    **self.parent_view.payload(),
                )
        except discord.NotFound:
            pass
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Item updated, but refreshing the list failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if self.return_item_embed:
            payload = TodoEmbeds.item_details_embed(final_list, final_item)
            await interaction.followup.send(
                ephemeral=True,
                **payload,
            )
            return

        await interaction.followup.send(ephemeral=True, content=f"Updated item #{self.item_number}.")


class TodoListItemsView(discord.ui.View):
    def __init__(
        self,
        todo_list: Dict[str, Any],
        items: List[Dict[str, Any]],
        sort: str,
        status_filter: str = "all",
        user_id: Optional[int] = None,
        view_scope: str = "list",
        guild_id: Optional[int] = None,
        page: int = 1,
        page_size: int = 5,
    ) -> None:
        super().__init__(timeout=300)
        self.todo_list = todo_list
        self._all_items = items
        self.items: List[Dict[str, Any]] = []
        self.sort = sort
        self.status_filter = (
            status_filter
            if status_filter
            in {
                "all",
                "todo",
                "in_progress",
                "done",
            }
            else "all"
        )
        self.user_id = user_id
        self.view_scope = view_scope
        self.guild_id = guild_id
        self.only_assigned_to_me = False
        self.page_size = max(1, min(page_size, 5))
        self.total_pages = 1
        self.page = max(1, page)
        self._apply_filters()
        self._build()

    def _page_slice(self) -> List[Dict[str, Any]]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.items[start:end]

    def payload(self) -> dict:
        return TodoEmbeds.list_items_page_embed(
            todo_list=self.todo_list,
            items=self._page_slice(),
            sort=self.sort,
            page=self.page,
            total_pages=self.total_pages,
            total_items=len(self.items),
            status_counts=TodoEmbeds._status_counts(self.items),
            mine_only=self.only_assigned_to_me,
            status_filter=self.status_filter,
        )

    async def _reload_items(self) -> None:
        if self.view_scope == "all_server":
            self._all_items = await asyncio.to_thread(
                TodoFunctions.list_items_on_guild,
                self.guild_id,
                self.sort,
            )
        else:
            self._all_items = await asyncio.to_thread(
                TodoFunctions.list_items_on_list,
                self.todo_list.get("_id"),
                self.sort,
            )
        self._apply_filters()

    def _apply_filters(self) -> None:
        filtered_items = list(self._all_items)
        if self.only_assigned_to_me and self.user_id is not None:
            filtered_items = [
                item
                for item in filtered_items
                if self.user_id in (item.get("assignees") or [])
            ]
        if self.status_filter != "all":
            filtered_items = [
                item
                for item in filtered_items
                if TodoFunctions.item_status(item) == self.status_filter
            ]
        self.items = filtered_items
        self.total_pages = max(1, math.ceil(len(self.items) / self.page_size))
        self.page = max(1, min(self.page, self.total_pages))

    async def _notify_missing_message(self, interaction: discord.Interaction) -> None:
        message = (
            "That todo list message is no longer available. "
            "Run `/todo list show` again."
        )
        try:
            if interaction.response.is_done():
                await interaction.followup.send(ephemeral=True, content=message)
            else:
                await interaction.response.send_message(ephemeral=True, content=message)
        except Exception:
            return

    async def _safe_refresh_message(self, interaction: discord.Interaction) -> bool:
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self, **self.payload())
            else:
                await interaction.response.edit_message(view=self, **self.payload())
            return True
        except discord.NotFound:
            await self._notify_missing_message(interaction)
            return False

    @staticmethod
    def _member_option_label(member: Any) -> str:
        display_name = str(getattr(member, "display_name", "") or getattr(member, "name", ""))
        username = str(getattr(member, "name", "")).strip()
        if display_name and username and display_name != username:
            return f"{display_name} (@{username})"[:100]
        return (display_name or username or "User")[:100]

    def _build_assignee_select_options(
        self,
        interaction: discord.Interaction,
        item: Dict[str, Any],
    ) -> List[discord.SelectOption]:
        assignees = item.get("assignees") or []
        current_assignee_id = assignees[0] if assignees else None

        options: List[discord.SelectOption] = []
        seen_values: set[str] = set()

        none_default = current_assignee_id is None
        options.append(
            discord.SelectOption(
                label="None (Unassign)",
                value="__none__",
                default=none_default,
            )
        )
        seen_values.add("__none__")

        me_value = "__me__"
        me_default = current_assignee_id == interaction.user.id
        options.append(
            discord.SelectOption(
                label="Me",
                value=me_value,
                default=me_default,
            )
        )
        seen_values.add(me_value)

        if current_assignee_id is not None and current_assignee_id != interaction.user.id:
            current_value = f"user:{current_assignee_id}"
            options.append(
                discord.SelectOption(
                    label=f"Current <@{current_assignee_id}>"[:100],
                    value=current_value,
                    default=True,
                )
            )
            seen_values.add(current_value)

        guild = interaction.guild
        members = []
        if guild is not None:
            members = list(getattr(interaction.channel, "members", None) or guild.members)

        for member in members:
            if getattr(member, "bot", False):
                continue
            member_id = getattr(member, "id", None)
            if member_id is None:
                continue
            value = f"user:{member_id}"
            if value in seen_values:
                continue

            options.append(
                discord.SelectOption(
                    label=self._member_option_label(member),
                    value=value,
                    default=(current_assignee_id == member_id),
                )
            )
            seen_values.add(value)
            if len(options) >= 25:
                break

        return options[:25]

    def _build_list_select_options(
        self,
        item: Dict[str, Any],
        list_docs: List[Dict[str, Any]],
    ) -> List[discord.SelectOption]:
        current_list_id = str(item.get("list_id") or "")
        current_list_name = str(item.get("list_name") or self.todo_list.get("name") or "Current list")

        options: List[discord.SelectOption] = []
        seen_ids: set[str] = set()

        for list_doc in list_docs:
            raw_id = list_doc.get("_id")
            if not raw_id:
                continue
            list_id = str(raw_id)
            if list_id in seen_ids:
                continue

            name = str(list_doc.get("name") or "Unnamed")
            scope = str(list_doc.get("scope") or "")
            channel_id = list_doc.get("channel_id")
            if scope == "personal":
                label = f"{name} (personal)"
            elif channel_id is not None:
                label = f"{name} (ch:{channel_id})"
            else:
                label = name

            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=list_id,
                    default=(current_list_id == list_id),
                )
            )
            seen_ids.add(list_id)
            if len(options) >= 25:
                break

        if current_list_id and current_list_id not in seen_ids:
            options.insert(
                0,
                discord.SelectOption(
                    label=current_list_name[:100],
                    value=current_list_id,
                    default=True,
                ),
            )

        return options[:25]

    def _build(self) -> None:
        self.clear_items()
        page_items = self._page_slice()

        for display_index, item in enumerate(page_items, start=1):
            item_id = str(item.get("_id") or "")
            item_no = item.get("item_no")
            item_status = TodoFunctions.item_status(item)
            complete_button = discord.ui.Button(
                label=f"✅ {display_index}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"todo_item_complete:{item_id}",
                row=0,
                disabled=(not item_id) or item_status == "done",
            )

            async def _callback(
                interaction: discord.Interaction,
                item_object_id: str = item_id,
                item_number: Any = item_no,
            ) -> None:
                await interaction.response.defer()
                if not item_object_id:
                    await interaction.followup.send(
                        ephemeral=True,
                        content="Couldn't complete that item.",
                    )
                    return
                updated = await asyncio.to_thread(
                    TodoFunctions.set_item_status,
                    item_object_id,
                    "done",
                )
                if not updated:
                    await interaction.followup.send(
                        ephemeral=True,
                        content=f"Couldn't complete item #{item_number}.",
                    )
                    return
                await self._reload_items()
                self._build()
                refreshed = await self._safe_refresh_message(interaction)
                if not refreshed:
                    return
                await interaction.followup.send(
                    ephemeral=True,
                    content=f"Marked item #{item_number} as done.",
                )

            complete_button.callback = _callback
            self.add_item(complete_button)

            edit_button = discord.ui.Button(
                label=f"✏️ {display_index}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"todo_item_edit:{item_id}",
                row=1,
                disabled=not item_id,
            )

            async def _edit_callback(
                interaction: discord.Interaction,
                item_data: Dict[str, Any] = item,
                item_number_value: Any = item_no,
                display_number: int = display_index,
            ) -> None:
                global _MODAL_SELECTS_SUPPORTED
                assignee_options = self._build_assignee_select_options(
                    interaction,
                    item_data,
                )
                list_options: List[discord.SelectOption] = []
                try:
                    list_docs = await asyncio.to_thread(
                        TodoFunctions.list_candidate_lists_for_item_scope,
                        item_data,
                        interaction.user.id,
                        25,
                    )
                    list_options = self._build_list_select_options(item_data, list_docs)
                except Exception:
                    list_options = []

                modal_item_number = (
                    item_number_value if item_number_value is not None else display_number
                )
                if _MODAL_SELECTS_SUPPORTED:
                    try:
                        await interaction.response.send_modal(
                            TodoItemEditModal(
                                parent_view=self,
                                item=item_data,
                                item_number=modal_item_number,
                                source_message=interaction.message,
                                assignee_options=assignee_options,
                                list_options=list_options,
                            )
                        )
                        return
                    except discord.HTTPException as exc:
                        if exc.code == 50035 and "must be one of (4,)" in str(exc):
                            _MODAL_SELECTS_SUPPORTED = False
                        else:
                            raise

                await interaction.response.send_modal(
                    TodoItemEditModal(
                        parent_view=self,
                        item=item_data,
                        item_number=modal_item_number,
                        source_message=interaction.message,
                    )
                )

            edit_button.callback = _edit_callback
            self.add_item(edit_button)

        prev_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="◀️",
            disabled=self.page <= 1,
            row=2,
        )
        refresh_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="🔄",
            row=2,
        )
        next_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="▶️",
            disabled=self.page >= self.total_pages,
            row=2,
        )
        sort_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="↕️",
            row=2,
        )
        filter_button = discord.ui.Button(
            style=(
                discord.ButtonStyle.success
                if self.only_assigned_to_me
                else discord.ButtonStyle.secondary
            ),
            emoji="👤",
            row=2,
            disabled=self.user_id is None,
        )

        async def _prev_callback(interaction: discord.Interaction) -> None:
            if self.page <= 1:
                await interaction.response.defer(ephemeral=True)
                return
            self.page -= 1
            self._build()
            await self._safe_refresh_message(interaction)

        async def _next_callback(interaction: discord.Interaction) -> None:
            if self.page >= self.total_pages:
                await interaction.response.defer(ephemeral=True)
                return
            self.page += 1
            self._build()
            await self._safe_refresh_message(interaction)

        async def _refresh_callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            await self._reload_items()
            self._build()
            await self._safe_refresh_message(interaction)

        async def _sort_toggle_callback(interaction: discord.Interaction) -> None:
            await interaction.response.defer()
            self.sort = "descending" if self.sort == "ascending" else "ascending"
            await self._reload_items()
            self._build()
            await self._safe_refresh_message(interaction)

        async def _mine_toggle_callback(interaction: discord.Interaction) -> None:
            if self.user_id is None:
                await interaction.response.defer(ephemeral=True)
                return
            await interaction.response.defer()
            self.only_assigned_to_me = not self.only_assigned_to_me
            await self._reload_items()
            self.page = 1
            self._build()
            await self._safe_refresh_message(interaction)

        prev_button.callback = _prev_callback
        refresh_button.callback = _refresh_callback
        next_button.callback = _next_callback
        sort_button.callback = _sort_toggle_callback
        filter_button.callback = _mine_toggle_callback

        self.add_item(prev_button)
        self.add_item(refresh_button)
        self.add_item(next_button)
        self.add_item(sort_button)
        self.add_item(filter_button)


class TodoReminderView(discord.ui.View):
    def __init__(
        self, todo_id: str, todo_name: str, user_id: Optional[int] = None
    ) -> None:
        super().__init__(timeout=3600)
        self.todo_id = todo_id
        self.todo_name = todo_name
        self.user_id = user_id

        button = discord.ui.Button(
            label="Complete",
            style=discord.ButtonStyle.success,
            custom_id=f"todo_reminder_complete:{todo_id}",
        )
        button.callback = self._on_complete
        self.add_item(button)

    async def _on_complete(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        updated = await asyncio.to_thread(
            TodoFunctions.complete_todo,
            self.todo_id,
            interaction.guild_id,
            self.user_id or interaction.user.id,
        )
        if not updated:
            await interaction.followup.send(
                ephemeral=True,
                content=f"Couldn't complete '{self.todo_name}'.",
            )
            return
        await interaction.followup.send(
            ephemeral=True,
            content=f"Marked '{self.todo_name}' as done.",
        )


class TodoEmbeds:
    _MAX_LIST_ITEMS_PREVIEW = 10

    @staticmethod
    def _status_filter_label(status_filter: str) -> str:
        if status_filter == "all":
            return "All"
        return TodoFunctions.status_label(status_filter)

    @staticmethod
    def _status_chip(status: str) -> str:
        normalized = (status or "").strip().lower()
        chips = {
            "todo": "🟢 To Do",
            "in_progress": "🟡 In Progress",
            "done": "✅ Done",
        }
        return chips.get(normalized, TodoFunctions.status_label(normalized))

    @staticmethod
    def _status_counts(items: List[Dict[str, Any]]) -> Dict[str, int]:
        counts = {"todo": 0, "in_progress": 0, "done": 0}
        for item in items:
            status = TodoFunctions.item_status(item)
            if status not in counts:
                continue
            counts[status] += 1
        return counts

    @staticmethod
    def _summary_line(total_items: int, status_counts: Dict[str, int]) -> str:
        return (
            f"Total: {total_items} | "
            f"🟢 To Do: {status_counts.get('todo', 0)} | "
            f"🟡 In Progress: {status_counts.get('in_progress', 0)} | "
            f"✅ Done: {status_counts.get('done', 0)}"
        )

    @staticmethod
    def _meta_line(sort: str, status_filter: str, mine_only: bool) -> str:
        sort_label = "Ascending" if sort == "ascending" else "Descending"
        status_label = TodoEmbeds._status_filter_label(status_filter)
        mine_label = "On" if mine_only else "Off"
        return f"Sort: {sort_label} | Status: {status_label} | Mine only: {mine_label}"

    @staticmethod
    def _due_line(due: Optional[Union[datetime.datetime, str]]) -> Optional[str]:
        if not due:
            return None

        def _parse_due_dt(
            value: Optional[Union[datetime.datetime, str]],
        ) -> Optional[datetime.datetime]:
            if isinstance(value, datetime.datetime):
                return value
            if isinstance(value, str):
                raw = value.strip()
                if not raw:
                    return None
                try:
                    return datetime.datetime.fromisoformat(raw)
                except ValueError:
                    if raw.endswith("Z"):
                        try:
                            return datetime.datetime.fromisoformat(raw[:-1] + "+00:00")
                        except ValueError:
                            return None
                    return None
            return None

        due_dt = _parse_due_dt(due)
        if due_dt is None:
            return f"🗓️ Due: {TodoFunctions.format_due(due)}"

        if due_dt.tzinfo is not None and due_dt.utcoffset() is not None:
            now = datetime.datetime.now(datetime.timezone.utc).astimezone(due_dt.tzinfo)
        else:
            now = datetime.datetime.now()

        due_for_epoch = due_dt
        if due_for_epoch.tzinfo is None or due_for_epoch.utcoffset() is None:
            local_tz = datetime.datetime.now().astimezone().tzinfo
            if local_tz is not None:
                due_for_epoch = due_for_epoch.replace(tzinfo=local_tz)
        unix_ts = int(due_for_epoch.timestamp())
        rel = f"<t:{unix_ts}:R>"

        if due_dt < now:
            return f"🔴 Overdue: {rel}"
        if due_dt.date() == now.date():
            return f"🟠 Due: {rel}"
        return f"🗓️ Due: {rel}"

    @staticmethod
    def _list_title(todo_list: Dict[str, Any]) -> str:
        list_name = str(todo_list.get("name") or "Unnamed")
        return f"Tasks • {list_name}"

    @staticmethod
    def _number_emoji(value: int) -> str:
        digits = {
            "0": "0️⃣",
            "1": "1️⃣",
            "2": "2️⃣",
            "3": "3️⃣",
            "4": "4️⃣",
            "5": "5️⃣",
            "6": "6️⃣",
            "7": "7️⃣",
            "8": "8️⃣",
            "9": "9️⃣",
        }
        return "".join(digits.get(ch, ch) for ch in str(value))

    @staticmethod
    def _format_due(due: Optional[Union[datetime.datetime, str]]) -> str:
        return TodoFunctions.format_due(due)

    @staticmethod
    def insert_todo_embed(
        name: str,
        description: Optional[str],
        due: Optional[Union[datetime.datetime, str]],
    ) -> dict:
        embed = discord.Embed(
            title="Todo Created",
            color=discord.Colour.green(),
        )
        lines = []
        if description:
            lines.append(str(description))
        if due:
            lines.append(f"📅 {TodoEmbeds._format_due(due)}")

        embed.add_field(
            name=name,
            value="\n".join(lines) if lines else "No details",
            inline=False,
        )

        return {"embed": embed}

    @staticmethod
    def todo_reminder_payload(todo: Dict[str, Any]) -> dict:
        name = str(todo.get("name") or "Todo")
        description = todo.get("description")
        due = todo.get("due")
        user_id = todo.get("user_id")
        todo_id = str(todo.get("_id") or "")

        embed = discord.Embed(
            title="Todo Reminder",
            color=discord.Colour.orange(),
        )
        lines = []
        if description:
            lines.append(str(description))
        if due:
            lines.append(f"Due: {TodoEmbeds._format_due(due)}")

        embed.add_field(
            name=name,
            value="\n".join(lines) if lines else "No details",
            inline=False,
        )

        payload: Dict[str, Any] = {"embed": embed}
        if user_id:
            payload["content"] = f"<@{user_id}>"
        if todo_id:
            payload["view"] = TodoReminderView(todo_id, name, user_id)
        return payload

    @staticmethod
    def list_todos_embed(
        todos: list[dict],
        mode: str,
        sort: str,
        page: int = 1,
        page_size: int = 5,
    ) -> dict:
        embed = discord.Embed(
            title="Todo List",
            color=discord.Colour.blurple(),
        )

        total = len(todos)
        if total == 0:
            embed.description = "No todos found."
            return {"embed": embed}

        page_size = max(1, page_size)
        total_pages = max(1, math.ceil(total / page_size))
        page = max(1, min(page, total_pages))

        start = (page - 1) * page_size
        end = start + page_size
        page_items = todos[start:end]

        for index, todo in enumerate(page_items, start=start + 1):
            name = str(todo.get("name") or "Untitled")
            description = todo.get("description")
            due_raw = todo.get("due")
            lines = []
            if description:
                lines.append(str(description))
            if due_raw:
                due = TodoEmbeds._format_due(due_raw)
                lines.append(f"📅 {due}")
            embed.add_field(
                name=f"{TodoEmbeds._number_emoji(index)} {name}",
                value="\n".join(lines),
                inline=False,
            )

        embed.description = f"Mode: {mode} | Sort: {sort}"
        embed.set_footer(text=f"Page {page}/{total_pages}")
        return {"embed": embed}

    @staticmethod
    def list_items_embed(
        todo_list: Dict[str, Any],
        items: List[Dict[str, Any]],
        sort: str,
        status_filter: str = "all",
    ) -> dict:
        embed = discord.Embed(
            title=TodoEmbeds._list_title(todo_list),
            color=discord.Colour.blurple(),
        )
        status_label = TodoEmbeds._status_filter_label(status_filter)

        if not items:
            embed.description = "No items in this list."
            embed.set_footer(text=f"Items: 0 | Sort: {sort} | Status: {status_label}")
            return {"embed": embed}

        for display_index, item in enumerate(
            items[: TodoEmbeds._MAX_LIST_ITEMS_PREVIEW], start=1
        ):
            number_emoji = TodoEmbeds._number_emoji(display_index)
            item_name = str(item.get("name") or "Untitled")
            status = TodoFunctions.status_label(TodoFunctions.item_status(item))
            list_name = str(item.get("list_name") or "").strip()
            text = TodoFunctions.item_text(item) or ""
            due_line = TodoEmbeds._due_line(item.get("due"))
            assignees = item.get("assignees") or []
            item_title = (
                f"{number_emoji} {item_name} [{status}] | {list_name}"
                if list_name
                else f"{number_emoji} {item_name} [{status}]"
            )
            value_lines = []
            description_line = TodoFunctions.truncate_multiline(text)
            if description_line and description_line.lower() != item_name.lower():
                value_lines.append(description_line)
            if due_line:
                value_lines.append(due_line)
            if assignees:
                mentions = " ".join(f"<@{uid}>" for uid in assignees)
                value_lines.append(f"👥 Assignees: {mentions}")
            if not value_lines:
                value_lines.append("No details")
            embed.add_field(
                name=item_title,
                value="\n".join(value_lines),
                inline=False,
            )

        if len(items) > TodoEmbeds._MAX_LIST_ITEMS_PREVIEW:
            remaining = len(items) - TodoEmbeds._MAX_LIST_ITEMS_PREVIEW
            embed.set_footer(
                text=(
                    f"Showing first {TodoEmbeds._MAX_LIST_ITEMS_PREVIEW} items "
                    f"({remaining} more) | Sort: {sort} | Status: {status_label}"
                )
            )
        else:
            embed.set_footer(
                text=f"Items: {len(items)} | Sort: {sort} | Status: {status_label}"
            )

        return {"embed": embed}

    @staticmethod
    def list_items_page_embed(
        todo_list: Dict[str, Any],
        items: List[Dict[str, Any]],
        sort: str,
        page: int,
        total_pages: int,
        total_items: int,
        status_counts: Optional[Dict[str, int]] = None,
        mine_only: bool = False,
        status_filter: str = "all",
    ) -> dict:
        embed = discord.Embed(
            title=TodoEmbeds._list_title(todo_list),
            color=discord.Colour.blurple(),
        )

        if not items:
            embed.description = "No items in this list."
            mine_filter = "Mine only: On" if mine_only else "Mine only: Off"
            status_label = TodoEmbeds._status_filter_label(status_filter)
            embed.set_footer(
                text=(
                    f"Page {page}/{total_pages} | Items: {total_items} | "
                    f"Sort: {sort} | Status: {status_label} | {mine_filter}"
                )
            )
            return {"embed": embed}

        for display_index, item in enumerate(items, start=1):
            number_emoji = TodoEmbeds._number_emoji(display_index)
            item_name = str(item.get("name") or "Untitled")
            status = TodoFunctions.status_label(TodoFunctions.item_status(item))
            list_name = str(item.get("list_name") or "").strip()
            text = TodoFunctions.item_text(item) or ""
            due_line = TodoEmbeds._due_line(item.get("due"))
            assignees = item.get("assignees") or []
            item_title = (
                f"{number_emoji} {item_name} [{status}] | {list_name}"
                if list_name
                else f"{number_emoji} {item_name} [{status}]"
            )
            value_lines = []
            description_line = TodoFunctions.truncate_multiline(text)
            if description_line and description_line.lower() != item_name.lower():
                value_lines.append(description_line)
            if due_line:
                value_lines.append(due_line)
            if assignees:
                mentions = " ".join(f"<@{uid}>" for uid in assignees)
                value_lines.append(f"👥 Assignees: {mentions}")
            if not value_lines:
                value_lines.append("No details")
            embed.add_field(
                name=item_title,
                value="\n".join(value_lines),
                inline=False,
            )

        mine_filter = "Mine only: On" if mine_only else "Mine only: Off"
        status_label = TodoEmbeds._status_filter_label(status_filter)
        embed.set_footer(
            text=(
                f"Page {page}/{total_pages} | Items: {total_items} | "
                f"Sort: {sort} | Status: {status_label} | {mine_filter}"
            )
        )
        return {"embed": embed}

    @staticmethod
    def item_details_embed(
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
    ) -> dict:
        item_no = item.get("item_no")
        text = TodoFunctions.item_text(item) or "No text"
        status = TodoFunctions.status_label(TodoFunctions.item_status(item))
        due_text = TodoEmbeds._due_line(item.get("due")) or "Due: Not set"
        assignees = item.get("assignees") or []
        mentions = " ".join(f"<@{uid}>" for uid in assignees) if assignees else "None"

        embed = discord.Embed(
            title=f"{todo_list.get('name') or 'List'} | Item #{item_no}",
            color=discord.Colour.blurple(),
            description=text if len(text) <= 3500 else text[:3497] + "...",
        )
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Due", value=due_text, inline=True)
        embed.add_field(name="Assignees", value=mentions, inline=False)

        return {"embed": embed}
