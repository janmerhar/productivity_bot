import asyncio
import datetime
import math
from typing import Optional, Union, List, Dict, Any

import discord

from classes.TodoFunctions import TodoFunctions
from classes.UserSettingsFunctions import UserSettingsFunctions
from services.due_datetime import DueDateService
from services.error_reporting import (
    UserVisibleError,
    ValidationError,
    handle_interaction_error,
)

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
                todo_name: str = TodoFunctions.task_name_from_item(todo),
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
        source_interaction: Optional[discord.Interaction] = None,
        assignee_options: Optional[List[discord.SelectOption]] = None,
        list_options: Optional[List[discord.SelectOption]] = None,
        return_item_embed: bool = False,
        refresh_source_as_item_embed: bool = False,
        locale_code: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> None:
        modal_title = f"Edit {TodoFunctions.task_name_from_item(item)}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.parent_view = parent_view
        self.item_id = str(item.get("_id") or "")
        self.item_number = item_number
        self.item_name = TodoFunctions.task_name_from_item(item)
        self.source_message = source_message
        self.source_interaction = source_interaction
        self.return_item_embed = return_item_embed
        self.refresh_source_as_item_embed = refresh_source_as_item_embed
        self.locale_code = DueDateService.normalize_locale_code(locale_code)
        self.timezone = timezone

        current_task = TodoFunctions.task_name_from_item(item) or "Untitled"
        current_description = TodoFunctions.item_body(item)

        current_status = TodoFunctions.item_status(item)
        due_value = TodoFunctions.item_due(item)
        current_due = (
            ""
            if not due_value
            else DueDateService.format_due(
                due_value,
                locale_code=self.locale_code,
                timezone=self.timezone,
            )
        )
        self.initial_due_raw = str(due_value) if due_value else None
        self.initial_due_display = current_due
        self.current_status = current_status
        self.current_list_id = str(item.get("list_id") or "")
        self.current_list_name = str(
            item.get("list_name")
            or TodoFunctions.display_list_name(parent_view.todo_list, "")
            or ""
        ).strip()
        current_assignee_id = TodoFunctions.item_assignee_id(item)
        current_assignee = (
            f"<@{current_assignee_id}>" if current_assignee_id is not None else "none"
        )
        self.assignee_select: Optional[discord.ui.Select] = None
        self.list_select: Optional[discord.ui.Select] = None
        self.assignee_select_label: Optional[discord.ui.Label] = None
        self.list_select_label: Optional[discord.ui.Label] = None
        self.assignee_input: Optional[discord.ui.TextInput] = None
        self.list_input: Optional[discord.ui.TextInput] = None

        self.task_input = discord.ui.TextInput(
            label="Todo",
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
        due_placeholder = DueDateService.due_placeholder(
            timezone=self.timezone,
            locale_code=self.locale_code,
        )
        self.due_input = discord.ui.TextInput(
            label="Due",
            placeholder=due_placeholder,
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
                )
                self.list_select = discord.ui.Select(
                    placeholder="List",
                    min_values=1,
                    max_values=1,
                    options=list_options[:25],
                )
                self.assignee_select_label = discord.ui.Label(
                    text="Assignee",
                    component=self.assignee_select,
                )
                self.list_select_label = discord.ui.Label(
                    text="List",
                    component=self.list_select,
                )
                self.add_item(self.assignee_select_label)
                self.add_item(self.list_select_label)
            except Exception:
                self.assignee_select = None
                self.list_select = None
                self.assignee_select_label = None
                self.list_select_label = None
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

    async def _edit_source_payload(self, **payload: Any) -> bool:
        if self.source_interaction is not None:
            try:
                await self.source_interaction.edit_original_response(**payload)
                return True
            except discord.NotFound:
                pass
            except discord.HTTPException:
                pass

        if self.source_message is None:
            return False

        await self.source_message.edit(**payload)
        return True

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
                self.timezone,
                self.locale_code,
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

        if self.source_message is not None and self.refresh_source_as_item_embed:
            try:
                payload = TodoEmbeds.item_details_embed(final_list, final_item)
                await self._edit_source_payload(**payload)
            except discord.NotFound:
                pass
            except Exception as exc:
                await handle_interaction_error(
                    interaction,
                    UserVisibleError(
                        "Item updated, but refreshing the item card failed.",
                        ephemeral=True,
                        cause=exc,
                    ),
                )
                return
        else:
            try:
                await self.parent_view._reload_items()
                self.parent_view._build()
                if self.source_message is not None:
                    await self._edit_source_payload(
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

        if self.source_message is None:
            await interaction.followup.send(
                ephemeral=True,
                content=f"Updated task {TodoFunctions.task_ref_from_item(final_item)}.",
            )


class TodoItemCreateModal(discord.ui.Modal):
    def __init__(
        self,
        parent_view: "TodoListItemsView",
        todo_list: Dict[str, Any],
        source_message: Optional[discord.Message],
        assignee_options: Optional[List[discord.SelectOption]] = None,
        list_options: Optional[List[discord.SelectOption]] = None,
        locale_code: Optional[str] = None,
        timezone: Optional[str] = None,
    ) -> None:
        modal_title = f"Add to {TodoFunctions.display_list_name(todo_list, 'List')}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.parent_view = parent_view
        self.todo_list = todo_list
        self.source_message = source_message
        self.locale_code = DueDateService.normalize_locale_code(locale_code)
        self.timezone = timezone
        self.current_list_id = str(todo_list.get("_id") or "")
        self.current_list_name = (
            TodoFunctions.display_list_name(todo_list, "List").strip() or "List"
        )
        self.scope_item: Dict[str, Any] = {
            "scope": str(todo_list.get("scope") or "channel"),
            "guild_id": todo_list.get("guild_id"),
            "channel_id": todo_list.get("channel_id"),
            "user_id": todo_list.get("user_id"),
            "list_id": todo_list.get("_id"),
            "list_name": self.current_list_name,
        }

        self.assignee_select: Optional[discord.ui.Select] = None
        self.list_select: Optional[discord.ui.Select] = None
        self.assignee_select_label: Optional[discord.ui.Label] = None
        self.list_select_label: Optional[discord.ui.Label] = None
        self.assignee_input: Optional[discord.ui.TextInput] = None
        self.list_input: Optional[discord.ui.TextInput] = None

        self.task_input = discord.ui.TextInput(
            label="Todo",
            style=discord.TextStyle.short,
            required=True,
            max_length=100,
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=800,
        )
        due_placeholder = DueDateService.due_placeholder(
            timezone=self.timezone,
            locale_code=self.locale_code,
        )
        self.due_input = discord.ui.TextInput(
            label="Due",
            placeholder=due_placeholder,
            required=False,
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
                )
                self.list_select = discord.ui.Select(
                    placeholder="List",
                    min_values=1,
                    max_values=1,
                    options=list_options[:25],
                )
                self.assignee_select_label = discord.ui.Label(
                    text="Assignee",
                    component=self.assignee_select,
                )
                self.list_select_label = discord.ui.Label(
                    text="List",
                    component=self.list_select,
                )
                self.add_item(self.assignee_select_label)
                self.add_item(self.list_select_label)
            except Exception:
                self.assignee_select = None
                self.list_select = None
                self.assignee_select_label = None
                self.list_select_label = None
                self.clear_items()
                self.add_item(self.task_input)
                self.add_item(self.description_input)
                self.add_item(self.due_input)

        if self.assignee_select is None or self.list_select is None:
            self.assignee_input = discord.ui.TextInput(
                label="Assignee",
                placeholder="none, me, user:<id>, <@id>, or ID",
                required=False,
                default="none",
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

        list_id = self.todo_list.get("_id")
        if not list_id:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "Creating from this view is only supported on a single list.",
                    ephemeral=True,
                ),
            )
            return

        try:
            target_list = self.todo_list
            if self.list_select is not None:
                list_token = (
                    self.list_select.values[0] if self.list_select.values else ""
                )
            else:
                list_token = (
                    str(self.list_input.value or "").strip()
                    if self.list_input is not None
                    else ""
                )
            if list_token:
                target_list = await asyncio.to_thread(
                    TodoFunctions.find_list_for_item_scope_by_token,
                    self.scope_item,
                    list_token,
                    interaction.user.id,
                )

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
                    str(self.assignee_input.value or "").strip()
                    if self.assignee_input is not None
                    else ""
                )
                if assignee_value:
                    assignee_id = TodoFunctions.parse_assignee_modal_input(
                        assignee_value,
                        interaction.user.id,
                    )
                else:
                    assignee_id = None
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(str(exc), ephemeral=True, cause=exc),
            )
            return

        task_text = str(self.task_input.value or "").strip()
        description_text = str(self.description_input.value or "").strip()
        item_text = task_text
        if description_text:
            item_text = f"{task_text}\n{description_text}"

        try:
            created_item, _ = await asyncio.to_thread(
                TodoFunctions.add_item_to_list,
                target_list,
                interaction.user.id,
                item_text,
                str(self.due_input.value or "").strip(),
                "todo",
                assignee_id,
                self.timezone,
                self.locale_code,
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
                    "Something went wrong while creating that item.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        target_list_id = str(target_list.get("_id") or "")
        try:
            await self.parent_view._reload_items()
            if target_list_id == self.current_list_id:
                if self.parent_view.sort == "ascending":
                    self.parent_view.page = self.parent_view.total_pages
                else:
                    self.parent_view.page = 1
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
                    "Item created, but refreshing the list failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if self.source_message is None or target_list_id != self.current_list_id:
            payload = TodoEmbeds.item_details_embed(target_list, created_item)
            await interaction.followup.send(
                ephemeral=True,
                **payload,
            )


class TodoListOptionsModal(discord.ui.Modal):
    def __init__(
        self,
        parent_view: "TodoListItemsView",
        source_message: Optional[discord.Message],
        assignee_options: Optional[List[discord.SelectOption]] = None,
        list_options: Optional[List[discord.SelectOption]] = None,
    ) -> None:
        list_name = (
            TodoFunctions.display_list_name(parent_view.todo_list, "List").strip()
            or "List"
        )
        modal_title = f"View Options • {list_name}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.parent_view = parent_view
        self.source_message = source_message
        self.assignee_select: Optional[discord.ui.Select] = None
        self.assignee_select_label: Optional[discord.ui.Label] = None
        self.assignee_input: Optional[discord.ui.TextInput] = None
        self.list_select: Optional[discord.ui.Select] = None
        self.list_select_label: Optional[discord.ui.Label] = None
        self.list_input: Optional[discord.ui.TextInput] = None
        self.search_input = discord.ui.TextInput(
            label="Search",
            placeholder="Task, description, list",
            required=False,
            default=parent_view.search_query,
            max_length=100,
        )

        self.sort_group = discord.ui.RadioGroup(
            custom_id="todo_list_options_sort",
            options=[
                discord.RadioGroupOption(
                    label="Ascending",
                    value="ascending",
                    default=parent_view.sort == "ascending",
                ),
                discord.RadioGroupOption(
                    label="Descending",
                    value="descending",
                    default=parent_view.sort == "descending",
                ),
            ],
        )
        self.status_group = discord.ui.RadioGroup(
            custom_id="todo_list_options_status",
            options=[
                discord.RadioGroupOption(
                    label="All",
                    value="all",
                    default=parent_view.status_filter == "all",
                ),
                discord.RadioGroupOption(
                    label="To Do",
                    value="todo",
                    default=parent_view.status_filter == "todo",
                ),
                discord.RadioGroupOption(
                    label="In Progress",
                    value="in_progress",
                    default=parent_view.status_filter == "in_progress",
                ),
                discord.RadioGroupOption(
                    label="Done",
                    value="done",
                    default=parent_view.status_filter == "done",
                ),
            ],
        )

        self.add_item(
            discord.ui.Label(
                text="Sort",
                component=self.sort_group,
            )
        )
        self.add_item(
            discord.ui.Label(
                text="Status",
                component=self.status_group,
            )
        )
        self.add_item(self.search_input)
        if assignee_options:
            try:
                self.assignee_select = discord.ui.Select(
                    placeholder="All tasks or choose assignees",
                    min_values=1,
                    max_values=max(1, min(len(assignee_options), 25)),
                    options=assignee_options[:25],
                )
                self.add_item(
                    discord.ui.Label(
                        text="Assignee",
                        description="Multiple selections use OR.",
                        component=self.assignee_select,
                    )
                )
            except Exception:
                self.assignee_select = None

        if self.assignee_select is None:
            self.assignee_input = discord.ui.TextInput(
                label="Assignee",
                placeholder="all, me, unassigned, @user, ID (comma-separated OR)",
                required=False,
                default=parent_view.assignee_filter_input_value()[:200],
                max_length=200,
            )
            self.add_item(self.assignee_input)
        if (
            parent_view.view_scope == "list"
            and parent_view.todo_list.get("_id") is not None
        ):
            current_list_name = (
                TodoFunctions.display_list_name(parent_view.todo_list, "List").strip()
                or "List"
            )
            if list_options:
                try:
                    self.list_select = discord.ui.Select(
                        placeholder="Current list",
                        min_values=1,
                        max_values=1,
                        options=list_options[:25],
                    )
                    self.list_select_label = discord.ui.Label(
                        text="List",
                        description="Optional unless you want to switch lists.",
                        component=self.list_select,
                    )
                    self.add_item(self.list_select_label)
                except Exception:
                    self.list_select = None
                    self.list_select_label = None

            if self.list_select is None:
                self.list_input = discord.ui.TextInput(
                    label="List",
                    placeholder="Existing list name or list ID",
                    required=False,
                    default=current_list_name[:80],
                    max_length=80,
                )
                self.add_item(self.list_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        sort_value = str(self.sort_group.value or "ascending")
        status_value = str(self.status_group.value or "all")
        search_query = self.parent_view.normalize_search_query(self.search_input.value)

        if sort_value not in {"ascending", "descending"}:
            sort_value = "ascending"
        if status_value not in {"all", "todo", "in_progress", "done"}:
            status_value = "all"

        assignee_filter_ids: List[int] = []
        assignee_filter_unassigned = False
        assignee_filter_label = "All"
        try:
            assignee_filter_ids, assignee_filter_unassigned = (
                self._resolve_assignee_filters(interaction)
            )
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(str(exc), ephemeral=True, cause=exc),
            )
            return
        assignee_filter_label = self.parent_view.format_assignee_filter_label(
            interaction,
            assignee_filter_ids,
            assignee_filter_unassigned,
        )

        current_list_id = str(self.parent_view.todo_list.get("_id") or "")
        current_list_name = (
            TodoFunctions.display_list_name(self.parent_view.todo_list, "List").strip()
            or "List"
        )
        list_token = ""
        if self.list_select is not None:
            list_token = self.list_select.values[0] if self.list_select.values else ""
        elif self.list_input is not None:
            list_token = str(self.list_input.value or "").strip()
            lowered_token = list_token.lower()
            if lowered_token == "personal":
                list_token = "__personal__"
            elif lowered_token in {
                "inbox",
                TodoFunctions._SERVER_INBOX_DISPLAY_NAME.lower(),
            }:
                list_token = "__server_inbox__"

        list_changed = False
        if list_token:
            if self.list_select is not None:
                list_changed = list_token != current_list_id
            else:
                normalized_current_name = current_list_name.lower()
                normalized_token = list_token.lower()
                list_changed = (
                    normalized_token != normalized_current_name
                    and normalized_token != current_list_id.lower()
                )

        if list_changed and self.parent_view.view_scope == "list":
            try:
                target_list = await asyncio.to_thread(
                    TodoFunctions.find_list_for_item_scope_by_token,
                    self.parent_view._current_scope_item(interaction.user.id),
                    list_token,
                    interaction.user.id,
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
                        "Something went wrong while switching lists.",
                        ephemeral=True,
                        cause=exc,
                    ),
                )
                return

            if target_list.get("_id") is not None:
                self.parent_view.todo_list = target_list

        self.parent_view.sort = sort_value
        self.parent_view.status_filter = status_value
        self.parent_view.search_query = search_query
        self.parent_view.assignee_filter_unassigned = assignee_filter_unassigned
        self.parent_view.assignee_filter_ids = assignee_filter_ids
        self.parent_view.assignee_filter_id = (
            assignee_filter_ids[0] if len(assignee_filter_ids) == 1 else None
        )
        self.parent_view.assignee_filter_label = assignee_filter_label
        self.parent_view.page = 1

        try:
            await self.parent_view._reload_items()
            self.parent_view._build()
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while updating the list options.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if self.source_message is None:
            await interaction.followup.send(
                ephemeral=True,
                view=self.parent_view,
                **self.parent_view.payload(),
            )
            return

        try:
            await self.source_message.edit(view=self.parent_view, **self.parent_view.payload())
        except discord.NotFound:
            await self.parent_view._notify_missing_message(interaction)
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Options updated, but refreshing the list failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

    def _resolve_assignee_filters(
        self,
        interaction: discord.Interaction,
    ) -> tuple[List[int], bool]:
        user_ids: List[int] = []
        seen_ids: set[int] = set()
        include_unassigned = False

        if self.assignee_select is not None:
            selected_values = list(self.assignee_select.values)
            if not selected_values or "__all__" in selected_values:
                return [], False

            for raw_value in selected_values:
                token = str(raw_value or "").strip()
                if token == "__me__":
                    resolved_id = interaction.user.id
                elif token == "__unassigned__":
                    include_unassigned = True
                    continue
                else:
                    resolved_id = TodoFunctions.parse_assignee_token(
                        token,
                        interaction.user.id,
                    )
                if resolved_id is None or resolved_id in seen_ids:
                    continue
                seen_ids.add(resolved_id)
                user_ids.append(int(resolved_id))
            return user_ids, include_unassigned

        raw_input = str(self.assignee_input.value or "").strip() if self.assignee_input else ""
        if not raw_input:
            return [], False

        tokens = [token.strip() for token in raw_input.split(",") if token.strip()]
        if not tokens:
            return [], False

        all_tokens = {"all", "any", "*", "__all__"}
        lowered_tokens = {token.lower() for token in tokens}
        if lowered_tokens & all_tokens:
            return [], False

        for token in tokens:
            lowered = token.lower()
            if lowered in {"none", "unassign", "unassigned", "clear", "__none__"}:
                include_unassigned = True
                continue
            resolved_id = TodoFunctions.parse_assignee_modal_input(
                token,
                interaction.user.id,
            )
            if resolved_id is None or resolved_id in seen_ids:
                continue
            seen_ids.add(resolved_id)
            user_ids.append(int(resolved_id))

        return user_ids, include_unassigned


class TodoListItemsView(discord.ui.View):
    def __init__(
        self,
        todo_list: Dict[str, Any],
        items: List[Dict[str, Any]],
        sort: str,
        status_filter: str = "all",
        assignee_filter_id: Optional[int] = None,
        assignee_filter_ids: Optional[List[int]] = None,
        assignee_filter_unassigned: bool = False,
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
        self.assignee_filter_unassigned = bool(assignee_filter_unassigned)
        resolved_assignee_ids = [
            int(value)
            for value in (assignee_filter_ids or [])
            if value is not None
        ]
        if not resolved_assignee_ids and assignee_filter_id is not None:
            resolved_assignee_ids = [int(assignee_filter_id)]
        self.assignee_filter_ids = list(dict.fromkeys(resolved_assignee_ids))
        self.assignee_filter_id = (
            self.assignee_filter_ids[0] if len(self.assignee_filter_ids) == 1 else None
        )
        self.user_id = user_id
        self.view_scope = view_scope
        self.guild_id = guild_id
        self.search_query = ""
        self.assignee_filter_label = self._assignee_filter_summary_label()
        self.page_size = max(1, min(page_size, 5))
        self.total_pages = 1
        self.page = max(1, page)
        self._apply_filters()
        self._build()

    def _page_slice(self) -> List[Dict[str, Any]]:
        start = (self.page - 1) * self.page_size
        end = start + self.page_size
        return self.items[start:end]

    def _page_item(self, slot_index: int) -> Optional[Dict[str, Any]]:
        page_items = self._page_slice()
        if 0 <= slot_index < len(page_items):
            return page_items[slot_index]
        return None

    def payload(self) -> dict:
        return TodoEmbeds.list_items_page_embed(
            todo_list=self.todo_list,
            items=self._page_slice(),
            sort=self.sort,
            page=self.page,
            total_pages=self.total_pages,
            total_items=len(self.items),
            status_counts=TodoEmbeds._status_counts(self.items),
            status_filter=self.status_filter,
            assignee_filter_label=self.assignee_filter_label,
            search_filter_label=self.search_filter_label(),
        )

    async def _reload_items(self) -> None:
        if self.view_scope in {"overview", "all_server"}:
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

    def _assignee_filter_mode(self) -> str:
        if self.assignee_filter_unassigned:
            if self.assignee_filter_ids:
                return "mixed"
            return "unassigned"
        if not self.assignee_filter_ids:
            return "all"
        if (
            len(self.assignee_filter_ids) == 1
            and self.user_id is not None
            and self.assignee_filter_ids[0] == self.user_id
        ):
            return "me"
        return "user"

    def _has_active_list_options(self) -> bool:
        return (
            self.sort != "ascending"
            or self.status_filter != "all"
            or bool(self.search_query)
            or self.assignee_filter_unassigned
            or bool(self.assignee_filter_ids)
        )

    @staticmethod
    def normalize_search_query(value: Optional[str]) -> str:
        return str(value or "").strip()

    def search_filter_label(self) -> str:
        text = str(self.search_query or "").strip()
        if not text:
            return "All"
        if len(text) <= 24:
            return text
        return f"{text[:21].rstrip()}..."

    def _assignee_filter_summary_label(self) -> str:
        if not self.assignee_filter_ids and not self.assignee_filter_unassigned:
            return "All"

        labels: List[str] = []
        if self.assignee_filter_ids:
            if len(self.assignee_filter_ids) == 1 and self.user_id is not None:
                if self.assignee_filter_ids[0] == self.user_id:
                    labels.append("Me")
                else:
                    labels.append("1 user")
            else:
                labels.append(
                    "Me"
                    if self.user_id is not None
                    and self.assignee_filter_ids == [self.user_id]
                    else f"{len(self.assignee_filter_ids)} users"
                )
        if self.assignee_filter_unassigned:
            labels.append("Unassigned")
        return " + ".join(labels)[:100]

    def assignee_filter_input_value(self) -> str:
        if not self.assignee_filter_ids and not self.assignee_filter_unassigned:
            return "all"

        tokens: List[str] = []
        for user_id in self.assignee_filter_ids:
            if self.user_id is not None and user_id == self.user_id:
                tokens.append("me")
            else:
                tokens.append(str(user_id))
        if self.assignee_filter_unassigned:
            tokens.append("unassigned")
        return ", ".join(tokens)

    def format_assignee_filter_label(
        self,
        interaction: discord.Interaction,
        assignee_filter_ids: List[int],
        assignee_filter_unassigned: bool,
    ) -> str:
        if not assignee_filter_ids and not assignee_filter_unassigned:
            return "All"

        labels: List[str] = []
        guild = interaction.guild
        for user_id in assignee_filter_ids:
            if self.user_id is not None and user_id == self.user_id:
                labels.append("Me")
                continue
            member = guild.get_member(user_id) if guild is not None else None
            label = str(
                getattr(member, "display_name", "")
                or getattr(member, "name", "")
                or f"User {user_id}"
            ).strip()
            labels.append(label[:30])
        if assignee_filter_unassigned:
            labels.append("Unassigned")
        if len(labels) <= 2:
            return " + ".join(labels)[:100]
        return f"{len(assignee_filter_ids)} users" + (
            " + Unassigned" if assignee_filter_unassigned else ""
        )

    def _current_scope_item(self, acting_user_id: Optional[int] = None) -> Dict[str, Any]:
        return {
            "scope": str(self.todo_list.get("scope") or "channel"),
            "guild_id": self.todo_list.get("guild_id"),
            "channel_id": self.todo_list.get("channel_id"),
            "user_id": self.todo_list.get("user_id")
            or self.user_id
            or acting_user_id,
            "list_id": self.todo_list.get("_id"),
            "list_name": TodoFunctions.display_list_name(self.todo_list, "List"),
        }

    @staticmethod
    def _search_text(item: Dict[str, Any]) -> str:
        parts = [
            TodoFunctions.task_name_from_item(item),
            TodoFunctions.item_text(item) or "",
            str(item.get("list_name") or ""),
        ]
        return " ".join(str(part or "") for part in parts).lower()

    async def open_options_modal(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message],
    ) -> None:
        global _MODAL_SELECTS_SUPPORTED

        list_options: List[discord.SelectOption] = []
        assignee_options: List[discord.SelectOption] = []
        if self.view_scope == "list" and self.todo_list.get("_id") is not None:
            scope_item = self._current_scope_item(interaction.user.id)
            try:
                list_docs = await asyncio.to_thread(
                    TodoFunctions.list_candidate_lists_for_item_scope,
                    scope_item,
                    interaction.user.id,
                    25,
                )
                list_options = self._build_list_select_options(scope_item, list_docs)
            except Exception:
                list_options = []
        try:
            assignee_options = self._build_assignee_filter_select_options(interaction)
        except Exception:
            assignee_options = []

        if _MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    TodoListOptionsModal(
                        parent_view=self,
                        source_message=source_message,
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
            TodoListOptionsModal(
                parent_view=self,
                source_message=source_message,
            )
        )

    async def open_create_modal(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message],
    ) -> None:
        global _MODAL_SELECTS_SUPPORTED

        if self.view_scope != "list" or self.todo_list.get("_id") is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="Open a specific list to create a task from this view.",
            )
            return

        modal_locale = str(getattr(interaction, "locale", "") or "").strip() or None
        try:
            modal_timezone = await asyncio.to_thread(
                UserSettingsFunctions.get_timezone,
                interaction.user.id,
            )
        except Exception:
            modal_timezone = None

        assignee_options = self._build_assignee_select_options(
            interaction,
            {"assignee_id": None},
        )
        scope_item = self._current_scope_item(interaction.user.id)
        list_options: List[discord.SelectOption] = []
        try:
            list_docs = await asyncio.to_thread(
                TodoFunctions.list_candidate_lists_for_item_scope,
                scope_item,
                interaction.user.id,
                25,
            )
            list_options = self._build_list_select_options(scope_item, list_docs)
        except Exception:
            list_options = []

        if _MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    TodoItemCreateModal(
                        parent_view=self,
                        todo_list=self.todo_list,
                        source_message=source_message,
                        assignee_options=assignee_options,
                        list_options=list_options,
                        locale_code=modal_locale,
                        timezone=modal_timezone,
                    )
                )
                return
            except discord.HTTPException as exc:
                if exc.code == 50035 and "must be one of (4,)" in str(exc):
                    _MODAL_SELECTS_SUPPORTED = False
                else:
                    raise

        await interaction.response.send_modal(
            TodoItemCreateModal(
                parent_view=self,
                todo_list=self.todo_list,
                source_message=source_message,
                locale_code=modal_locale,
                timezone=modal_timezone,
            )
        )

    def _apply_filters(self) -> None:
        filtered_items = list(self._all_items)
        if self.search_query:
            normalized_query = self.search_query.lower()
            filtered_items = [
                item
                for item in filtered_items
                if normalized_query in self._search_text(item)
            ]
        if self.assignee_filter_ids or self.assignee_filter_unassigned:
            allowed_ids = set(self.assignee_filter_ids)
            filtered_items = [
                item
                for item in filtered_items
                if (
                    bool(
                        allowed_ids.intersection(
                            TodoFunctions.item_assignee_ids(item)
                        )
                    )
                    or (
                        self.assignee_filter_unassigned
                        and TodoFunctions.item_assignee_id(item) is None
                    )
                )
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

    async def _resolve_list_for_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        list_id = item.get("list_id")
        if not list_id:
            return self.todo_list
        try:
            resolved_list = await asyncio.to_thread(
                TodoFunctions.fetch_todo_list_by_id,
                list_id,
            )
            if resolved_list is not None:
                return resolved_list
        except Exception:
            pass
        return self.todo_list

    async def _open_item_details(
        self,
        interaction: discord.Interaction,
        item: Optional[Dict[str, Any]],
    ) -> None:
        item_id = str((item or {}).get("_id") or "").strip()
        if not item_id:
            await interaction.response.defer(ephemeral=True)
            return

        try:
            current_item = await asyncio.to_thread(
                TodoFunctions.fetch_todo,
                item_id,
                interaction.guild_id,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while loading that item.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if current_item is None:
            await self._reload_items()
            self._build()
            await self._safe_refresh_message(interaction)
            return

        todo_list = await self._resolve_list_for_item(current_item)
        payload = TodoEmbeds.item_details_embed(todo_list, current_item)
        await interaction.response.send_message(
            ephemeral=True,
            **payload,
        )

    @staticmethod
    def _member_option_label(member: Any) -> str:
        display_name = str(
            getattr(member, "display_name", "") or getattr(member, "name", "")
        )
        username = str(getattr(member, "name", "")).strip()
        if display_name and username and display_name != username:
            return f"{display_name} (@{username})"[:100]
        return (display_name or username or "User")[:100]

    def _build_assignee_select_options(
        self,
        interaction: discord.Interaction,
        item: Dict[str, Any],
    ) -> List[discord.SelectOption]:
        current_assignee_id = TodoFunctions.item_assignee_id(item)

        options: List[discord.SelectOption] = []
        seen_values: set[str] = set()

        none_default = current_assignee_id is None
        options.append(
            discord.SelectOption(
                label="None",
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

        if (
            current_assignee_id is not None
            and current_assignee_id != interaction.user.id
        ):
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
            members = list(
                getattr(interaction.channel, "members", None) or guild.members
            )

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

    def _build_assignee_filter_select_options(
        self,
        interaction: discord.Interaction,
    ) -> List[discord.SelectOption]:
        selected_ids = list(self.assignee_filter_ids)
        seen_values: set[str] = set()
        options: List[discord.SelectOption] = [
            discord.SelectOption(
                label="All tasks",
                value="__all__",
                default=(
                    not selected_ids and not self.assignee_filter_unassigned
                ),
            ),
            discord.SelectOption(
                label="Me",
                value="__me__",
                default=(
                    self.user_id is not None and self.user_id in selected_ids
                ),
            ),
            discord.SelectOption(
                label="Unassigned",
                value="__unassigned__",
                default=self.assignee_filter_unassigned,
            ),
        ]
        seen_values.update({"__all__", "__me__", "__unassigned__"})

        current_user_id = self.user_id or interaction.user.id
        for selected_id in selected_ids:
            if selected_id == current_user_id:
                continue
            value = f"user:{selected_id}"
            if value in seen_values:
                continue
            options.append(
                discord.SelectOption(
                    label=f"Current <@{selected_id}>"[:100],
                    value=value,
                    default=True,
                )
            )
            seen_values.add(value)

        guild = interaction.guild
        members = []
        if guild is not None:
            members = list(
                getattr(interaction.channel, "members", None) or guild.members
            )

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
                    default=(member_id in selected_ids),
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
        current_list_name = str(
            item.get("list_name")
            or TodoFunctions.display_list_name(self.todo_list, "Current list")
            or "Current list"
        )
        current_scope = TodoFunctions._normalize_scope(
            str(item.get("scope") or "channel")
        )
        current_channel_id = item.get("channel_id")
        guild_id = item.get("guild_id")

        options: List[discord.SelectOption] = []
        seen_ids: set[str] = set()
        has_default = False

        reserve_special = 0
        if current_scope == "channel" and guild_id is not None:
            reserve_special = 1  # personal target
        max_doc_options = max(1, 25 - reserve_special - 1)  # reserve fallback current

        for list_doc in list_docs:
            raw_id = list_doc.get("_id")
            if not raw_id:
                continue
            list_id = str(raw_id)
            if list_id in seen_ids:
                continue

            name = TodoFunctions.display_list_name(list_doc, "Unnamed")
            scope = str(list_doc.get("scope") or "")
            channel_id = list_doc.get("channel_id")
            if scope == "channel" and channel_id is not None:
                label = name if name.startswith("#") else f"#{name}"
            elif scope == "channel":
                label = name if TodoFunctions.is_server_inbox_list(list_doc) else f"Server - {name}"
            elif scope == "personal":
                label = (
                    "Personal"
                    if name.strip().lower() == "personal"
                    else f"Personal - {name}"
                )
            else:
                label = name

            is_default = current_list_id == list_id
            options.append(
                discord.SelectOption(
                    label=label[:100],
                    value=list_id,
                    default=is_default,
                )
            )
            if is_default:
                has_default = True
            seen_ids.add(list_id)
            if len(options) >= max_doc_options:
                break

        if current_list_id and current_list_id not in seen_ids:
            fallback_label = current_list_name
            if current_scope == "channel" and current_channel_id is not None:
                fallback_label = (
                    current_list_name
                    if current_list_name.startswith("#")
                    else f"#{current_list_name}"
                )
            elif current_scope == "personal":
                fallback_label = (
                    "Personal"
                    if current_list_name.strip().lower() == "personal"
                    else f"Personal - {current_list_name}"
                )
            options.insert(
                0,
                discord.SelectOption(
                    label=fallback_label[:100],
                    value=current_list_id,
                    default=True,
                ),
            )
            has_default = True

        if current_scope == "channel" and guild_id is not None:
            top_options: List[discord.SelectOption] = [
                discord.SelectOption(
                    label="Personal",
                    value="__personal__",
                    default=False,
                )
            ]
            options = top_options + options

        return options[:25]

    def _build(self) -> None:
        self.clear_items()

        for slot_index in range(self.page_size):
            display_index = slot_index + 1
            item = self._page_item(slot_index)
            item_id = str((item or {}).get("_id") or "")
            has_item = item is not None

            info_button = discord.ui.Button(
                label=str(display_index),
                style=discord.ButtonStyle.secondary,
                custom_id=f"todo_item_info:{item_id or display_index}",
                row=0,
                disabled=not has_item,
            )

            async def _info_callback(
                interaction: discord.Interaction,
                item_data: Optional[Dict[str, Any]] = item,
            ) -> None:
                await self._open_item_details(interaction, item_data)

            info_button.callback = _info_callback
            self.add_item(info_button)

        prev_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="◀️",
            disabled=self.page <= 1,
            row=1,
        )
        add_button = discord.ui.Button(
            style=discord.ButtonStyle.success,
            emoji="➕",
            row=1,
            disabled=(self.view_scope != "list") or (self.todo_list.get("_id") is None),
        )
        next_button = discord.ui.Button(
            style=discord.ButtonStyle.secondary,
            emoji="▶️",
            disabled=self.page >= self.total_pages,
            row=1,
        )
        options_button = discord.ui.Button(
            style=(
                discord.ButtonStyle.success
                if self._has_active_list_options()
                else discord.ButtonStyle.secondary
            ),
            emoji="🔎",
            row=1,
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

        async def _add_callback(interaction: discord.Interaction) -> None:
            await self.open_create_modal(
                interaction,
                source_message=interaction.message,
            )

        async def _options_callback(interaction: discord.Interaction) -> None:
            await self.open_options_modal(
                interaction,
                source_message=interaction.message,
            )

        prev_button.callback = _prev_callback
        next_button.callback = _next_callback
        add_button.callback = _add_callback
        options_button.callback = _options_callback

        self.add_item(prev_button)
        self.add_item(next_button)
        self.add_item(add_button)
        self.add_item(options_button)


class TodoDeleteConfirmModal(discord.ui.Modal):
    def __init__(
        self,
        item_id: str,
        item_name: str,
        list_name: str,
        source_message: Optional[discord.Message],
    ) -> None:
        modal_title = f"Delete {TodoFunctions.task_ref(item_name)}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.item_id = item_id
        self.item_name = str(item_name).strip()
        self.list_name = list_name
        self.source_message = source_message
        self.add_item(
            discord.ui.TextDisplay(
                f"This will permanently delete {TodoFunctions.task_ref(self.item_name)} "
                f"from `{self.list_name or 'List'}`."
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        deleted = await asyncio.to_thread(TodoFunctions.delete_item, self.item_id)

        if not deleted:
            await interaction.followup.send(
                ephemeral=True,
                content=f"Couldn't delete task {TodoFunctions.task_ref(self.item_name)}.",
            )
            return

        if self.source_message is not None:
            try:
                deleted_payload = TodoEmbeds.deleted_item_embed(
                    self.list_name or "List",
                    self.item_name,
                )
                await self.source_message.edit(view=None, **deleted_payload)
            except discord.NotFound:
                pass
            except Exception:
                await interaction.followup.send(
                    ephemeral=True,
                    content="Item deleted, but updating the card failed.",
                )
                return
            return

        deleted_payload = TodoEmbeds.deleted_item_embed(
            self.list_name or "List",
            self.item_name,
        )
        await interaction.followup.send(
            ephemeral=True,
            **deleted_payload,
        )


class TodoAssignSelectModal(discord.ui.Modal):
    def __init__(
        self,
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
        source_message: Optional[discord.Message],
        assignee_options: List[discord.SelectOption],
    ) -> None:
        modal_title = (
            f"Assign {TodoFunctions.task_ref(TodoFunctions.task_name_from_item(item))}"
        )
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.todo_list = todo_list
        self.item_id = str(item.get("_id") or "")
        self.item_name = TodoFunctions.task_name_from_item(item)
        self.source_message = source_message

        self.assignee_select = discord.ui.Select(
            placeholder="Assignee",
            min_values=1,
            max_values=1,
            options=assignee_options[:25],
        )
        self.assignee_select_label = discord.ui.Label(
            text="Assignee",
            component=self.assignee_select,
        )
        self.add_item(self.assignee_select_label)

    async def _resolve_list_for_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        list_id = item.get("list_id")
        if not list_id:
            return self.todo_list
        try:
            resolved_list = await asyncio.to_thread(
                TodoFunctions.fetch_todo_list_by_id,
                list_id,
            )
            if resolved_list is not None:
                return resolved_list
        except Exception:
            pass
        return self.todo_list

    async def _refresh_source_card(
        self,
        interaction: discord.Interaction,
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
    ) -> bool:
        if self.source_message is None:
            return False
        payload = TodoEmbeds.item_details_embed(todo_list, item)
        try:
            await self.source_message.edit(**payload)
            return True
        except discord.NotFound:
            return False
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Todo updated, but refreshing the card failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return False

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not self.item_id:
            await handle_interaction_error(
                interaction,
                ValidationError("That item could not be assigned.", ephemeral=True),
            )
            return

        selected_token = (
            self.assignee_select.values[0]
            if self.assignee_select.values
            else "__none__"
        )

        try:
            assignee_id = TodoFunctions.parse_assignee_token(
                selected_token,
                interaction.user.id,
            )
            updated_item = await asyncio.to_thread(
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
                    "Something went wrong while updating assignment.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not updated_item:
            await handle_interaction_error(
                interaction,
                UserVisibleError("That item could not be assigned.", ephemeral=True),
            )
            return

        updated_list = await self._resolve_list_for_item(updated_item)
        await self._refresh_source_card(interaction, updated_list, updated_item)


class TodoAssignPickerView(discord.ui.View):
    def __init__(
        self,
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
        source_message: Optional[discord.Message],
        assignee_options: Optional[List[discord.SelectOption]] = None,
    ) -> None:
        super().__init__(timeout=180)
        self.todo_list = todo_list
        self.item_id = str(item.get("_id") or "")
        self.item_number = item.get("item_no")
        self.item_name = TodoFunctions.task_name_from_item(item)
        self.guild_id = item.get("guild_id")
        self.source_message = source_message

        self.selected_assignee_token: Optional[str] = None
        self.assignee_select: Optional[discord.ui.Select] = None

        if assignee_options:
            select = discord.ui.Select(
                placeholder="Assignee",
                min_values=1,
                max_values=1,
                options=assignee_options[:25],
                row=0,
            )
            select.callback = self._on_select_assignee
            self.assignee_select = select
            self.add_item(select)
            default_option = next(
                (opt for opt in assignee_options if getattr(opt, "default", False)),
                assignee_options[0],
            )
            self.selected_assignee_token = default_option.value

    def _disable_components(self) -> None:
        for child in self.children:
            if isinstance(child, (discord.ui.Button, discord.ui.Select)):
                child.disabled = True

    @staticmethod
    def _build_assignee_select_options(
        interaction: discord.Interaction,
        item: Dict[str, Any],
    ) -> List[discord.SelectOption]:
        current_assignee_id = TodoFunctions.item_assignee_id(item)

        options: List[discord.SelectOption] = []
        seen_values: set[str] = set()

        options.append(
            discord.SelectOption(
                label="None",
                value="__none__",
                default=current_assignee_id is None,
            )
        )
        seen_values.add("__none__")

        options.append(
            discord.SelectOption(
                label="Me",
                value="__me__",
                default=current_assignee_id == interaction.user.id,
            )
        )
        seen_values.add("__me__")

        if (
            current_assignee_id is not None
            and current_assignee_id != interaction.user.id
        ):
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
            members = list(
                getattr(interaction.channel, "members", None) or guild.members
            )

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
                    label=TodoListItemsView._member_option_label(member),
                    value=value,
                    default=(current_assignee_id == member_id),
                )
            )
            seen_values.add(value)
            if len(options) >= 25:
                break

        return options[:25]

    async def _on_select_assignee(self, interaction: discord.Interaction) -> None:
        if self.assignee_select is None or not self.assignee_select.values:
            await interaction.response.defer()
            return

        selected_value = self.assignee_select.values[0]
        self.selected_assignee_token = selected_value

        label = selected_value
        if selected_value == "__none__":
            label = "None"
        elif selected_value == "__me__":
            label = f"Me (<@{interaction.user.id}>)"
        elif selected_value.startswith("user:"):
            raw_id = selected_value.split(":", 1)[1].strip()
            if raw_id.isdigit():
                label = f"<@{raw_id}>"

        await interaction.response.edit_message(
            content=f"Selected assignee: {label}",
            view=self,
        )

    async def _resolve_list_for_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        list_id = item.get("list_id")
        if not list_id:
            return self.todo_list
        try:
            resolved_list = await asyncio.to_thread(
                TodoFunctions.fetch_todo_list_by_id,
                list_id,
            )
            if resolved_list is not None:
                return resolved_list
        except Exception:
            pass
        return self.todo_list

    async def _refresh_source_card(
        self,
        interaction: discord.Interaction,
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
    ) -> bool:
        if self.source_message is None:
            return False
        payload = TodoEmbeds.item_details_embed(todo_list, item)
        try:
            await self.source_message.edit(**payload)
            return True
        except discord.NotFound:
            return False
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Todo updated, but refreshing the card failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return False

    async def _apply_assignment(
        self,
        interaction: discord.Interaction,
        assignee_id: Optional[int],
    ) -> bool:
        updated_item = await asyncio.to_thread(
            TodoFunctions.set_item_assignee,
            self.item_id,
            assignee_id,
        )
        if not updated_item:
            return False
        updated_list = await self._resolve_list_for_item(updated_item)
        await self._refresh_source_card(interaction, updated_list, updated_item)
        return True

    @discord.ui.button(emoji="✅", style=discord.ButtonStyle.primary, row=1)
    async def assign_selected(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if not self.item_id:
            await interaction.response.send_message(
                ephemeral=True,
                content="That item could not be assigned.",
            )
            return

        target_token = self.selected_assignee_token
        if not target_token:
            await interaction.response.send_message(
                ephemeral=True,
                content="Select an assignee first.",
            )
            return

        try:
            target_user_id = TodoFunctions.parse_assignee_token(
                target_token,
                interaction.user.id,
            )
        except ValueError:
            await interaction.response.send_message(
                ephemeral=True,
                content="Please select a valid assignee option.",
            )
            return

        await interaction.response.defer(ephemeral=True)
        assigned = await self._apply_assignment(interaction, target_user_id)
        self._disable_components()

        if not assigned:
            try:
                await interaction.edit_original_response(view=self)
            except Exception:
                pass
            await interaction.followup.send(
                ephemeral=True,
                content=f"Couldn't assign task {TodoFunctions.task_ref(self.item_name)}.",
            )
            return

        try:
            if target_user_id is None:
                message = f"Unassigned task {TodoFunctions.task_ref(self.item_name)}."
            else:
                message = (
                    f"Assigned task {TodoFunctions.task_ref(self.item_name)} "
                    f"to <@{target_user_id}>."
                )
            await interaction.edit_original_response(
                content=message,
                view=self,
            )
        except Exception:
            pass

    @discord.ui.button(emoji="➖", style=discord.ButtonStyle.secondary, row=1)
    async def unassign(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if not self.item_id:
            await interaction.response.send_message(
                ephemeral=True,
                content="That item could not be updated.",
            )
            return

        await interaction.response.defer(ephemeral=True)
        unassigned = await self._apply_assignment(interaction, None)
        self._disable_components()

        if not unassigned:
            try:
                await interaction.edit_original_response(view=self)
            except Exception:
                pass
            await interaction.followup.send(
                ephemeral=True,
                content=f"Couldn't unassign task {TodoFunctions.task_ref(self.item_name)}.",
            )
            return

        try:
            await interaction.edit_original_response(
                content=f"Unassigned task {TodoFunctions.task_ref(self.item_name)}.",
                view=self,
            )
        except Exception:
            pass

    @discord.ui.button(emoji="✖️", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        self._disable_components()
        await interaction.response.edit_message(
            content="Assignment cancelled.",
            view=self,
        )


class TodoItemActionsView(discord.ui.View):
    def __init__(
        self,
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
    ) -> None:
        super().__init__(timeout=900)
        self.todo_list = todo_list
        self.item_id = str(item.get("_id") or "")
        self.item_number = item.get("item_no")
        self.item_name = TodoFunctions.task_name_from_item(item)
        self.guild_id = item.get("guild_id")

        item_status = TodoFunctions.item_status(item)
        self._apply_progress_button_state(item_status)
        if not self.item_id:
            self.complete_todo.disabled = True
        self.edit_todo.disabled = not self.item_id
        self.delete_todo.disabled = not self.item_id
        self.duplicate_todo.disabled = not self.item_id
        self.assign_to_user.disabled = (not self.item_id) or self.guild_id is None

    @staticmethod
    def _next_progress_status(current_status: str) -> Optional[str]:
        if current_status == "todo":
            return "in_progress"
        if current_status == "in_progress":
            return "done"
        return None

    def _apply_progress_button_state(self, current_status: str) -> None:
        if current_status == "todo":
            self.complete_todo.style = discord.ButtonStyle.primary
            self.complete_todo.emoji = "🟡"
            self.complete_todo.disabled = False
            return
        if current_status == "in_progress":
            self.complete_todo.style = discord.ButtonStyle.success
            self.complete_todo.emoji = "✅"
            self.complete_todo.disabled = False
            return

        self.complete_todo.style = discord.ButtonStyle.secondary
        self.complete_todo.emoji = "✅"
        self.complete_todo.disabled = True

    async def _resolve_list_for_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        list_id = item.get("list_id")
        if not list_id:
            return self.todo_list
        try:
            resolved_list = await asyncio.to_thread(
                TodoFunctions.fetch_todo_list_by_id,
                list_id,
            )
            if resolved_list is not None:
                return resolved_list
        except Exception:
            pass
        return self.todo_list

    async def _load_current_item_and_list(
        self,
    ) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        if not self.item_id:
            return None, None

        current_item = await asyncio.to_thread(
            TodoFunctions.fetch_todo,
            self.item_id,
            self.guild_id,
        )
        if current_item is None:
            return None, None

        current_list = await self._resolve_list_for_item(current_item)
        return current_list, current_item

    async def _refresh_source_card(
        self,
        interaction: discord.Interaction,
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
    ) -> bool:
        payload = TodoEmbeds.item_details_embed(todo_list, item)
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(**payload)
            else:
                await interaction.response.edit_message(**payload)
            return True
        except discord.NotFound:
            source_message = interaction.message
            if source_message is None:
                return False
            try:
                await source_message.edit(**payload)
                return True
            except discord.NotFound:
                return False
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Todo updated, but refreshing the card failed.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return False

    @discord.ui.button(emoji="✏️", style=discord.ButtonStyle.secondary, row=0)
    async def edit_todo(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        global _MODAL_SELECTS_SUPPORTED
        current_list, current_item = await self._load_current_item_and_list()
        if current_list is None or current_item is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="That item no longer exists.",
            )
            return

        try:
            items = await asyncio.to_thread(
                TodoFunctions.list_items_on_list,
                current_list["_id"],
                "ascending",
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                UserVisibleError(
                    "Something went wrong while loading that item.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        parent_view = TodoListItemsView(
            todo_list=current_list,
            items=items,
            sort="ascending",
            status_filter="all",
            user_id=interaction.user.id,
            view_scope="list",
            guild_id=interaction.guild_id,
        )
        assignee_options = parent_view._build_assignee_select_options(
            interaction,
            current_item,
        )
        list_options: List[discord.SelectOption] = []
        try:
            list_docs = await asyncio.to_thread(
                TodoFunctions.list_candidate_lists_for_item_scope,
                current_item,
                interaction.user.id,
                25,
            )
            list_options = parent_view._build_list_select_options(
                current_item, list_docs
            )
        except Exception:
            list_options = []

        modal_item_number = current_item.get("item_no") or self.item_number
        modal_locale = str(getattr(interaction, "locale", "") or "").strip()
        if not modal_locale:
            modal_locale = None
        try:
            modal_timezone = await asyncio.to_thread(
                UserSettingsFunctions.get_timezone,
                interaction.user.id,
            )
        except Exception:
            modal_timezone = None
        if _MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    TodoItemEditModal(
                        parent_view=parent_view,
                        item=current_item,
                        item_number=modal_item_number,
                        source_message=interaction.message,
                        source_interaction=interaction,
                        assignee_options=assignee_options,
                        list_options=list_options,
                        refresh_source_as_item_embed=True,
                        locale_code=modal_locale,
                        timezone=modal_timezone,
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
                parent_view=parent_view,
                item=current_item,
                item_number=modal_item_number,
                source_message=interaction.message,
                source_interaction=interaction,
                refresh_source_as_item_embed=True,
                locale_code=modal_locale,
                timezone=modal_timezone,
            )
        )

    @discord.ui.button(emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def complete_todo(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self.item_id:
            await interaction.followup.send(
                ephemeral=True,
                content="Couldn't complete that item.",
            )
            return

        current_list, current_item = await self._load_current_item_and_list()
        if current_list is None or current_item is None:
            await interaction.followup.send(
                ephemeral=True,
                content="That item no longer exists.",
            )
            return

        current_status = TodoFunctions.item_status(current_item)
        next_status = self._next_progress_status(current_status)
        if next_status is None:
            await self._refresh_source_card(interaction, current_list, current_item)
            return

        updated_item = await asyncio.to_thread(
            TodoFunctions.set_item_status,
            self.item_id,
            next_status,
        )
        if not updated_item:
            await interaction.followup.send(
                ephemeral=True,
                content=f"Couldn't update task {TodoFunctions.task_ref(self.item_name)}.",
            )
            return

        updated_list = await self._resolve_list_for_item(updated_item)
        await self._refresh_source_card(interaction, updated_list, updated_item)

    @discord.ui.button(emoji="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def delete_todo(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        if not self.item_id:
            await interaction.response.send_message(
                ephemeral=True,
                content="That item could not be deleted.",
            )
            return

        await interaction.response.send_modal(
            TodoDeleteConfirmModal(
                item_id=self.item_id,
                item_name=self.item_name,
                list_name=TodoFunctions.display_list_name(self.todo_list, "List"),
                source_message=interaction.message,
            )
        )

    @discord.ui.button(emoji="📄", style=discord.ButtonStyle.primary, row=0)
    async def duplicate_todo(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        if not self.item_id:
            await interaction.followup.send(
                ephemeral=True,
                content="That item could not be duplicated.",
            )
            return

        current_list, current_item = await self._load_current_item_and_list()
        if current_list is None or current_item is None:
            await interaction.followup.send(
                ephemeral=True,
                content="That item no longer exists.",
            )
            return

        try:
            duplicated_item, _ = await asyncio.to_thread(
                TodoFunctions.add_item_to_list,
                current_list,
                interaction.user.id,
                TodoFunctions.item_text(current_item),
                None,
                "todo",
                None,
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
                    "Something went wrong while duplicating that item.",
                    ephemeral=True,
                    cause=exc,
                ),
            )
            return

        if not duplicated_item:
            await interaction.followup.send(
                ephemeral=True,
                content="That item could not be duplicated.",
            )
            return

        payload = TodoEmbeds.item_details_embed(current_list, duplicated_item)
        await interaction.followup.send(
            ephemeral=True,
            content="Duplicated todo.",
            **payload,
        )

    @discord.ui.button(emoji="👥", style=discord.ButtonStyle.secondary, row=0)
    async def assign_to_user(
        self,
        interaction: discord.Interaction,
        _: discord.ui.Button,
    ) -> None:
        global _MODAL_SELECTS_SUPPORTED
        current_list, current_item = await self._load_current_item_and_list()
        if current_list is None or current_item is None:
            await interaction.response.send_message(
                ephemeral=True,
                content="That item no longer exists.",
            )
            return

        assignee_options = TodoAssignPickerView._build_assignee_select_options(
            interaction,
            current_item,
        )

        if _MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(
                    TodoAssignSelectModal(
                        todo_list=current_list,
                        item=current_item,
                        source_message=interaction.message,
                        assignee_options=assignee_options,
                    )
                )
                return
            except discord.HTTPException as exc:
                if exc.code == 50035 and "must be one of (4,)" in str(exc):
                    _MODAL_SELECTS_SUPPORTED = False
                else:
                    raise

        assign_view = TodoAssignPickerView(
            todo_list=current_list,
            item=current_item,
            source_message=interaction.message,
            assignee_options=assignee_options,
        )
        await interaction.response.send_message(
            ephemeral=True,
            content="Pick who should own this task.",
            view=assign_view,
        )


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
    def _meta_line(
        sort: str,
        status_filter: str,
        assignee_filter_label: str = "All",
    ) -> str:
        sort_label = "Ascending" if sort == "ascending" else "Descending"
        status_label = TodoEmbeds._status_filter_label(status_filter)
        assignee_label = str(assignee_filter_label or "All").strip() or "All"
        return (
            f"Sort: {sort_label} | Status: {status_label} | "
            f"Assignee: {assignee_label}"
        )

    @staticmethod
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

    @staticmethod
    def _due_relative(due: Optional[Union[datetime.datetime, str]]) -> Optional[str]:
        due_dt = TodoEmbeds._parse_due_dt(due)
        if due_dt is None:
            return None

        due_for_epoch = due_dt
        if due_for_epoch.tzinfo is None or due_for_epoch.utcoffset() is None:
            local_tz = datetime.datetime.now().astimezone().tzinfo
            if local_tz is not None:
                due_for_epoch = due_for_epoch.replace(tzinfo=local_tz)
        unix_ts = int(due_for_epoch.timestamp())
        return f"<t:{unix_ts}:R>"

    @staticmethod
    def _due_line(due: Optional[Union[datetime.datetime, str]]) -> Optional[str]:
        if not due:
            return None

        due_dt = TodoEmbeds._parse_due_dt(due)
        if due_dt is None:
            return f"🗓️ Due: {DueDateService.format_due(due)}"

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
        list_name = TodoFunctions.display_list_name(todo_list, "Unnamed")
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
        return DueDateService.format_due(due)

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
    def todo_reminder_payload(
        todo: Dict[str, Any],
        todo_list: Optional[Dict[str, Any]] = None,
    ) -> dict:
        user_id = todo.get("created_by_user_id") or todo.get("user_id")
        payload = TodoEmbeds.item_details_embed(
            todo_list or {"name": str(todo.get("list_name") or "List")},
            todo,
        )
        if user_id:
            payload["content"] = f"<@{user_id}>"
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
            name = TodoFunctions.task_name_from_item(todo) or "Untitled"
            description = TodoFunctions.item_body(todo)
            due_raw = TodoFunctions.item_due(todo)
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
    def list_description_embed(
        title: str,
        description: Optional[str] = None,
        color: Optional[discord.Colour] = None,
    ) -> dict:
        embed = discord.Embed(
            title=(str(title or "").strip() or "Todo List")[:256],
            description=(str(description or "").strip() or None),
            color=color or discord.Colour.blurple(),
        )

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
            item_name = TodoFunctions.task_name_from_item(item) or "Untitled"
            status = TodoFunctions.status_label(TodoFunctions.item_status(item))
            list_name = str(item.get("list_name") or "").strip()
            text = TodoFunctions.item_text(item) or ""
            due_line = TodoEmbeds._due_line(TodoFunctions.item_due(item))
            assignee_id = TodoFunctions.item_assignee_id(item)
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
            if assignee_id is not None:
                value_lines.append(f"👤 Assignee: <@{assignee_id}>")
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
        status_filter: str = "all",
        assignee_filter_label: str = "All",
        search_filter_label: str = "All",
    ) -> dict:
        embed = discord.Embed(
            title=TodoEmbeds._list_title(todo_list),
            color=discord.Colour.blurple(),
        )

        if not items:
            embed.description = "No items in this list."
            status_label = TodoEmbeds._status_filter_label(status_filter)
            embed.set_footer(
                text=(
                    f"Page {page}/{total_pages} | Items: {total_items} | "
                    f"Sort: {sort} | Status: {status_label} | "
                    f"Search: {search_filter_label} | Assignee: {assignee_filter_label}"
                )
            )
            return {"embed": embed}

        for display_index, item in enumerate(items, start=1):
            number_emoji = TodoEmbeds._number_emoji(display_index)
            item_name = TodoFunctions.task_name_from_item(item) or "Untitled"
            status = TodoFunctions.status_label(TodoFunctions.item_status(item))
            list_name = str(item.get("list_name") or "").strip()
            text = TodoFunctions.item_text(item) or ""
            due_line = TodoEmbeds._due_line(TodoFunctions.item_due(item))
            assignee_id = TodoFunctions.item_assignee_id(item)
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
            if assignee_id is not None:
                value_lines.append(f"👤 Assignee: <@{assignee_id}>")
            if not value_lines:
                value_lines.append("No details")
            embed.add_field(
                name=item_title,
                value="\n".join(value_lines),
                inline=False,
            )

        status_label = TodoEmbeds._status_filter_label(status_filter)
        embed.set_footer(
            text=(
                f"Page {page}/{total_pages} | Items: {total_items} | "
                f"Sort: {sort} | Status: {status_label} | "
                f"Search: {search_filter_label} | Assignee: {assignee_filter_label}"
            )
        )
        return {"embed": embed}

    @staticmethod
    def list_directory_embed(
        server_lists: List[Dict[str, Any]],
        personal_lists: List[Dict[str, Any]],
    ) -> dict:
        embed = discord.Embed(
            title="Todo List Directory",
            color=discord.Colour.blurple(),
        )

        if not server_lists and not personal_lists:
            embed.description = "No todo lists available."
            return {"embed": embed}

        if server_lists:
            server_lines = []
            for entry in server_lists:
                name = str(entry.get("name") or "Unnamed")
                count = int(entry.get("item_count") or 0)
                label = str(entry.get("label") or "").strip()
                if label:
                    server_lines.append(f"• {label}: `{name}` ({count})")
                else:
                    server_lines.append(f"• `{name}` ({count})")
            embed.add_field(
                name="Server",
                value="\n".join(server_lines),
                inline=False,
            )

        if personal_lists:
            personal_lines = []
            for entry in personal_lists:
                name = str(entry.get("name") or "Unnamed")
                count = int(entry.get("item_count") or 0)
                label = str(entry.get("label") or "").strip()
                if label:
                    personal_lines.append(f"• {label}: `{name}` ({count})")
                else:
                    personal_lines.append(f"• `{name}` ({count})")
            embed.add_field(
                name="Personal",
                value="\n".join(personal_lines),
                inline=False,
            )

        total_lists = len(server_lists) + len(personal_lists)
        total_items = sum(int(entry.get("item_count") or 0) for entry in server_lists)
        total_items += sum(int(entry.get("item_count") or 0) for entry in personal_lists)
        embed.set_footer(text=f"Lists: {total_lists} | Items: {total_items}")
        return {"embed": embed}

    @staticmethod
    def list_directory_page_embed(
        entries: List[Dict[str, Any]],
        *,
        page: int,
        total_pages: int,
        total_lists: int,
        total_items: int,
        sort_direction: str = "ascending",
    ) -> dict:
        embed = discord.Embed(
            title="Todo List Directory",
            color=discord.Colour.blurple(),
        )

        if not entries:
            embed.description = "No todo lists available."
            embed.set_footer(
                text=(
                    f"Page {page}/{total_pages} | Lists: {total_lists} | "
                    f"Items: {total_items} | Sort: {sort_direction}"
                )
            )
            return {"embed": embed}

        for display_index, entry in enumerate(entries, start=1):
            number_emoji = TodoEmbeds._number_emoji(display_index)
            name = str(entry.get("name") or "Unnamed").strip() or "Unnamed"
            scope = str(entry.get("scope") or "List").strip() or "List"
            label = str(entry.get("label") or "").strip()
            count = int(entry.get("item_count") or 0)

            title_parts = [f"{number_emoji} {name}", f"[{scope}]"]
            if label:
                title_parts.append(f"| {label}")

            embed.add_field(
                name=" ".join(title_parts),
                value=f"Items: {count}",
                inline=False,
            )

        embed.set_footer(
            text=(
                f"Page {page}/{total_pages} | Lists: {total_lists} | "
                f"Items: {total_items} | Sort: {sort_direction}"
            )
        )
        return {"embed": embed}

    @staticmethod
    def item_details_embed(
        todo_list: Dict[str, Any],
        item: Dict[str, Any],
        include_actions: bool = True,
    ) -> dict:
        text = TodoFunctions.item_text(item) or "No text"
        task_name = TodoFunctions.task_name_from_item(item)
        status = TodoFunctions.status_label(TodoFunctions.item_status(item))
        due_text = TodoEmbeds._due_relative(TodoFunctions.item_due(item)) or "Not set"
        assignee_id = TodoFunctions.item_assignee_id(item)
        mention = f"<@{assignee_id}>" if assignee_id is not None else "None"

        embed = discord.Embed(
            title=f"{TodoFunctions.display_list_name(todo_list, 'List')} | {task_name}",
            color=discord.Colour.blurple(),
            description=text if len(text) <= 3500 else text[:3497] + "...",
        )
        embed.add_field(name="Status", value=status, inline=True)
        embed.add_field(name="Due", value=due_text, inline=True)
        embed.add_field(name="Assignee", value=mention, inline=False)

        payload: Dict[str, Any] = {"embed": embed}
        if include_actions:
            payload["view"] = TodoItemActionsView(todo_list, item)
        return payload

    @staticmethod
    def deleted_item_embed(list_name: str, item_name: str) -> dict:
        embed = discord.Embed(
            title=f"{list_name or 'List'} | {item_name or 'Untitled'}",
            description="This todo was deleted.",
            color=discord.Colour.dark_grey(),
        )
        return {"embed": embed}
