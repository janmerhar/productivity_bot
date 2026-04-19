import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, Optional

import discord

from classes.TogglFunctions import TogglFunctions


def _option_label(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    return (text or fallback)[:100]


class TogglTimeEntryEditModal(discord.ui.Modal, title="Edit Toggl Timer"):
    def __init__(
        self,
        toggl: TogglFunctions,
        timer_data: dict[str, Any],
        project_options: list[discord.SelectOption],
        tag_options: list[discord.SelectOption],
        tags_disabled: bool,
        on_saved: Callable[[discord.Interaction, dict[str, Any]], Awaitable[None]],
        response_ephemeral: bool = True,
    ) -> None:
        super().__init__()
        self._toggl = toggl
        self._timer_data = dict(timer_data or {})
        self._on_saved = on_saved
        self._response_ephemeral = bool(response_ephemeral)
        self._workspace_id = (
            self._timer_data.get("workspace_id")
            or self._timer_data.get("wid")
            or self._toggl.workspace_id
        )

        self.description_input = discord.ui.TextInput(
            label="Description",
            placeholder="Leave blank to clear",
            required=False,
            max_length=300,
            default=str(self._timer_data.get("description") or "")[:300],
        )
        self.add_item(self.description_input)

        self.billable_select = discord.ui.Select(
            placeholder="Billable",
            min_values=1,
            max_values=1,
            options=self._build_billable_options(),
        )
        self.billable_select_label = discord.ui.Label(
            text="Billable",
            component=self.billable_select,
        )
        self.add_item(self.billable_select_label)

        self.project_select = discord.ui.Select(
            placeholder="Project",
            min_values=1,
            max_values=1,
            options=project_options,
        )
        self.project_select_label = discord.ui.Label(
            text="Project",
            component=self.project_select,
        )
        self.add_item(self.project_select_label)

        self.tags_select = discord.ui.Select(
            placeholder="Tags",
            min_values=0,
            max_values=max(1, min(len(tag_options), 25)),
            options=tag_options,
            required=False,
            disabled=tags_disabled,
        )
        self.tags_select_label = discord.ui.Label(
            text="Tags",
            component=self.tags_select,
        )
        self.add_item(self.tags_select_label)

    def _build_billable_options(self) -> list[discord.SelectOption]:
        current_value = self._timer_data.get("billable")
        return [
            discord.SelectOption(
                label="Not set",
                value="__none__",
                default=current_value is None,
            ),
            discord.SelectOption(
                label="Yes",
                value="true",
                default=current_value is True,
            ),
            discord.SelectOption(
                label="No",
                value="false",
                default=current_value is False,
            ),
        ]

    @classmethod
    def build_form_options(
        cls,
        toggl: TogglFunctions,
        timer_data: dict[str, Any],
    ) -> dict[str, Any]:
        workspace_id = (
            timer_data.get("workspace_id")
            or timer_data.get("wid")
            or toggl.workspace_id
        )
        tag_options, tags_disabled = cls._build_tag_options(
            toggl,
            timer_data,
            workspace_id=workspace_id,
        )
        return {
            "project_options": cls._build_project_options(
                toggl,
                timer_data,
                workspace_id=workspace_id,
            ),
            "tag_options": tag_options,
            "tags_disabled": tags_disabled,
        }

    @staticmethod
    def _build_project_options(
        toggl: TogglFunctions,
        timer_data: dict[str, Any],
        *,
        workspace_id: Optional[int],
    ) -> list[discord.SelectOption]:
        raw_project_id = timer_data.get("project_id") or timer_data.get("pid")
        try:
            current_project_id = int(raw_project_id) if raw_project_id is not None else None
        except (TypeError, ValueError):
            current_project_id = None
        options = [
            discord.SelectOption(
                label="None",
                value="__none__",
                default=current_project_id is None,
            )
        ]

        if workspace_id is None:
            return options

        projects = toggl.findProjectsLike(
            "",
            workspace_id=workspace_id,
            limit=24,
        )
        current_project = None
        if current_project_id is not None:
            current_project = toggl.getProjectById(
                project_id=current_project_id,
                workspace_id=workspace_id,
            )

        seen_ids = set()
        for project in [current_project, *projects]:
            if not isinstance(project, dict):
                continue
            project_id = project.get("id")
            if project_id is None or project_id in seen_ids:
                continue
            seen_ids.add(project_id)
            options.append(
                discord.SelectOption(
                    label=_option_label(project.get("name"), f"Project #{project_id}"),
                    value=str(project_id),
                    default=project_id == current_project_id,
                )
            )
            if len(options) >= 25:
                break

        return options

    @staticmethod
    def _build_tag_options(
        toggl: TogglFunctions,
        timer_data: dict[str, Any],
        *,
        workspace_id: Optional[int],
    ) -> tuple[list[discord.SelectOption], bool]:
        current_tags = []
        for tag in timer_data.get("tags") or []:
            cleaned_tag = str(tag or "").strip()
            if cleaned_tag and cleaned_tag not in current_tags:
                current_tags.append(cleaned_tag)

        if workspace_id is None:
            if current_tags:
                return (
                    [
                        discord.SelectOption(
                            label=_option_label(tag, tag),
                            value=tag,
                            default=True,
                        )
                        for tag in current_tags[:25]
                    ],
                    False,
                )
            return ([discord.SelectOption(label="No tags available", value="__none__")], True)

        tags = toggl.findTagsLike(
            "",
            workspace_id=workspace_id,
            limit=25,
        )

        option_names = []
        for tag in current_tags:
            if tag not in option_names:
                option_names.append(tag)
        for tag_data in tags:
            tag_name = str(tag_data.get("name") or "").strip()
            if tag_name and tag_name not in option_names:
                option_names.append(tag_name)
            if len(option_names) >= 25:
                break

        if not option_names:
            return ([discord.SelectOption(label="No tags available", value="__none__")], True)

        return (
            [
                discord.SelectOption(
                    label=_option_label(tag_name, "Unnamed tag"),
                    value=tag_name,
                    default=tag_name in current_tags,
                )
                for tag_name in option_names
            ],
            False,
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=self._response_ephemeral)

        workspace_id = self._workspace_id
        time_entry_id = self._timer_data.get("id")
        if workspace_id is None or time_entry_id is None:
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                content="This timer does not include enough data to edit.",
            )
            return

        project_value = self.project_select.values[0] if self.project_select.values else "__none__"
        if project_value == "__none__":
            project_id = None
        else:
            try:
                project_id = int(project_value)
            except ValueError:
                await interaction.followup.send(
                    ephemeral=self._response_ephemeral,
                    content="That project selection is invalid.",
                )
                return

        billable_value = self.billable_select.values[0] if self.billable_select.values else "__none__"
        if billable_value == "true":
            billable = True
        elif billable_value == "false":
            billable = False
        else:
            billable = None

        updated_tags = []
        if not self.tags_select.disabled:
            updated_tags = [
                str(tag).strip()
                for tag in self.tags_select.values
                if str(tag).strip() and str(tag).strip() != "__none__"
            ]

        description = str(self.description_input.value or "").strip() or None

        try:
            updated_timer = await asyncio.to_thread(
                self._toggl.updateTimeEntry,
                workspace_id,
                time_entry_id,
                timer_data=self._timer_data,
                billable=billable,
                description=description,
                pid=project_id,
                project_id=project_id,
                tags=updated_tags,
                task_id=self._timer_data.get("task_id"),
                tid=self._timer_data.get("task_id") or self._timer_data.get("tid"),
            )
        except Exception:
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                content="I couldn't update that Toggl timer right now. Please try again.",
            )
            return

        if not isinstance(updated_timer, dict) or updated_timer.get("id") is None:
            await interaction.followup.send(
                ephemeral=self._response_ephemeral,
                content="Toggl rejected that timer edit request.",
            )
            return

        await self._on_saved(interaction, updated_timer)
