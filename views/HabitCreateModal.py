import asyncio
from typing import Any, Optional

import discord

from classes.HabitFunctions import HabitFunctions
from classes.UserSettingsFunctions import UserSettingsFunctions
from embeds.HabitEmbeds import HabitEmbeds
from services.discord_helpers import normalize_habit_target
from services.error_reporting import ValidationError, handle_interaction_error
from services.visibility import inherit_ephemeral_from_interaction
from views.HabitActionView import HabitActionView

_MODAL_SELECTS_SUPPORTED = True


class HabitCreateModal(discord.ui.Modal):
    def __init__(
        self,
        cog: Any,
        *,
        user_id: int,
        scope_value: str,
        target_channel_id: Optional[int],
        response_ephemeral: bool,
        guild_id: Optional[int],
        channel_id: Optional[int],
        include_scope_select: bool = True,
        title: str = "Add Habit",
        habit_id: Optional[str] = None,
        default_habit: Optional[str] = None,
        default_description: Optional[str] = None,
        default_reminder: Optional[str] = None,
        source_view: Optional["HabitCreatedActionView"] = None,
        source_message: Optional[discord.Message] = None,
    ) -> None:
        super().__init__(title=title)
        self._cog = cog
        self._user_id = int(user_id)
        self._scope_value = str(scope_value or "channel")
        self._target_channel_id = target_channel_id
        self._response_ephemeral = bool(response_ephemeral)
        self._guild_id = guild_id
        self._channel_id = channel_id
        self._habit_id = str(habit_id or "").strip() or None
        self._source_view = source_view
        self._source_message = source_message
        self.scope_select: Optional[discord.ui.Select] = None
        self.scope_select_label: Optional[discord.ui.Label] = None

        self.habit_input = discord.ui.TextInput(
            label="Habit",
            style=discord.TextStyle.short,
            required=True,
            default=str(default_habit or ""),
        )
        self.description_input = discord.ui.TextInput(
            label="Description",
            style=discord.TextStyle.paragraph,
            required=False,
            default=str(default_description or ""),
        )
        self.reminder_input = discord.ui.TextInput(
            label="Reminder",
            style=discord.TextStyle.short,
            required=False,
            placeholder="8am, 20:30",
            default=str(default_reminder or ""),
        )

        self.add_item(self.habit_input)
        self.add_item(self.description_input)
        self.add_item(self.reminder_input)

        if include_scope_select:
            try:
                scope_options = self._build_scope_options()
                if len(scope_options) > 1:
                    self.scope_select = discord.ui.Select(
                        placeholder="Scope",
                        min_values=1,
                        max_values=1,
                        options=scope_options,
                    )
                    self.scope_select_label = discord.ui.Label(
                        text="Scope",
                        component=self.scope_select,
                    )
                    self.add_item(self.scope_select_label)
            except Exception:
                self.scope_select = None
                self.scope_select_label = None

    def _build_scope_options(self) -> list[discord.SelectOption]:
        options: list[discord.SelectOption] = []
        if self._guild_id is not None and self._channel_id is not None:
            default_current = (
                self._scope_value == "channel"
                and self._target_channel_id == self._channel_id
            )
            options.append(
                discord.SelectOption(
                    label="This Channel",
                    value="current",
                    default=default_current,
                )
            )
            guild = self._cog.client.get_guild(self._guild_id)
            if guild is not None:
                member = guild.get_member(self._user_id)
                for channel in guild.text_channels:
                    if len(options) >= 24:
                        break
                    if channel.id == self._channel_id:
                        continue
                    if member is not None and not channel.permissions_for(member).view_channel:
                        continue
                    options.append(
                        discord.SelectOption(
                            label=f"#{channel.name}"[:100],
                            value=f"channel:{channel.id}",
                            default=(
                                self._scope_value == "channel"
                                and self._target_channel_id == channel.id
                            ),
                        )
                    )
        options.append(
            discord.SelectOption(
                label="Personal",
                value="personal",
                default=self._scope_value == "personal",
            )
        )
        return options

    async def _submit_create(
        self,
        interaction: discord.Interaction,
        *,
        reminder_value: Optional[str],
        timezone: Optional[str],
        selected_scope: str,
        selected_channel_id: Optional[int],
    ) -> None:
        try:
            document, reminder_time, reminder_failed = await self._cog._persist_habit(
                interaction=interaction,
                habit=str(self.habit_input.value or ""),
                description=str(self.description_input.value or "").strip() or None,
                reminder=reminder_value,
                ephemeral=self._response_ephemeral,
                timezone=timezone,
                scope_value=selected_scope,
                target_channel_id=selected_channel_id,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
            return

        refresh_method = getattr(self._source_view, "refresh_message", None)
        if callable(refresh_method):
            try:
                await refresh_method(
                    interaction,
                    source_message=self._source_message,
                    jump_to_last_page=True,
                )
            except TypeError:
                try:
                    await refresh_method(
                        interaction,
                        source_message=self._source_message,
                    )
                except Exception:
                    pass
            except Exception:
                pass

        await self._cog._send_created_habit_response(
            interaction,
            document=document,
            reminder_time=reminder_time,
            reminder_failed=reminder_failed,
            ephemeral=self._response_ephemeral,
        )

    async def _submit_edit(
        self,
        interaction: discord.Interaction,
        *,
        reminder_value: Optional[str],
        timezone: Optional[str],
        selected_scope: str,
        selected_channel_id: Optional[int],
    ) -> None:
        if self._habit_id is None or self._source_view is None:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "This edit form is no longer available.",
                    ephemeral=self._response_ephemeral,
                ),
                ephemeral=self._response_ephemeral,
            )
            return

        try:
            document, _, reminder_failed = await self._cog._persist_habit_update(
                interaction=interaction,
                habit_id=self._habit_id,
                habit=str(self.habit_input.value or ""),
                description=str(self.description_input.value or "").strip() or None,
                reminder=reminder_value,
                ephemeral=self._response_ephemeral,
                timezone=timezone,
                scope_value=selected_scope,
                target_channel_id=selected_channel_id,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self._response_ephemeral,
            )
            return

        self._source_view.habit_id = str(document.get("_id") or self._source_view.habit_id)
        self._source_view.habit_name = str(
            document.get("name") or self._source_view.habit_name or "Habit"
        )
        self._source_view.scope_value = HabitFunctions._normalize_scope(
            str(document.get("scope") or "channel")
        )
        self._source_view.target_channel_id = document.get("channel_id")
        self._source_view.response_ephemeral = self._response_ephemeral

        refreshed = await self._source_view.refresh_message(
            interaction,
            source_message=self._source_message,
        )
        if not refreshed:
            payload = HabitEmbeds.habit_item_embed(
                document,
                HabitFunctions.today_status(document),
                HabitFunctions.recent_progress(document, days=5),
            )
            if reminder_failed:
                payload["content"] = (
                    "Habit updated, but I couldn't schedule the reminder."
                )
            payload["view"] = self._source_view
            try:
                posted_message = await interaction.followup.send(
                    ephemeral=self._response_ephemeral,
                    wait=True,
                    **payload,
                )
                self._source_view.message = posted_message
            except TypeError:
                await interaction.followup.send(
                    ephemeral=self._response_ephemeral,
                    **payload,
                )
            return

        if reminder_failed:
            await interaction.followup.send(
                "Habit updated, but I couldn't schedule the reminder.",
                ephemeral=self._response_ephemeral,
            )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=self._response_ephemeral)

        reminder_value = str(self.reminder_input.value or "").strip() or None
        timezone = await asyncio.to_thread(
            UserSettingsFunctions.get_timezone,
            interaction.user.id,
        )

        if reminder_value and not timezone:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "To save a reminder from this form, set your timezone with `/settings set timezone` first.",
                    ephemeral=self._response_ephemeral,
                ),
            )
            return

        selected_scope = self._scope_value
        selected_channel_id = self._target_channel_id
        if self.scope_select is not None and self.scope_select.values:
            try:
                selected_scope, selected_channel_id, _ = normalize_habit_target(
                    interaction,
                    self.scope_select.values[0],
                )
            except ValueError as exc:
                await handle_interaction_error(
                    interaction,
                    ValidationError(
                        str(exc),
                        ephemeral=self._response_ephemeral,
                        cause=exc,
                    ),
                )
                return

        if self._habit_id is not None:
            await self._submit_edit(
                interaction,
                reminder_value=reminder_value,
                timezone=timezone,
                selected_scope=selected_scope,
                selected_channel_id=selected_channel_id,
            )
            return

        await self._submit_create(
            interaction,
            reminder_value=reminder_value,
            timezone=timezone,
            selected_scope=selected_scope,
            selected_channel_id=selected_channel_id,
        )


def _format_reminder_input(reminder_time) -> Optional[str]:
    if reminder_time is None:
        return None
    try:
        return reminder_time.strftime("%H:%M")
    except AttributeError:
        return None


class HabitDeleteConfirmModal(discord.ui.Modal):
    def __init__(
        self,
        parent_view: "HabitCreatedActionView",
        *,
        source_message: Optional[discord.Message],
    ) -> None:
        habit_name = str(parent_view.habit_name or "").strip()
        modal_title = f"Delete {habit_name or 'Habit'}"
        if len(modal_title) > 45:
            modal_title = modal_title[:42].rstrip() + "..."
        super().__init__(title=modal_title)
        self.parent_view = parent_view
        self.source_message = source_message

        if habit_name:
            habit_ref = f"`{habit_name[:80]}`"
        else:
            habit_ref = "this habit"
        self.add_item(
            discord.ui.TextDisplay(
                f"This will permanently delete {habit_ref}."
            )
        )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.parent_view._confirm_delete(
            interaction,
            source_message=self.source_message,
        )


class HabitCreatedActionView(HabitActionView):
    def __init__(
        self,
        cog: Any,
        *,
        habit_id: str,
        habit_name: str,
        user_id: int,
        scope_value: str,
        target_channel_id: Optional[int],
        response_ephemeral: bool,
        timeout: float | None = 300,
    ) -> None:
        self._cog = cog
        self.scope_value = str(scope_value or "channel")
        self.target_channel_id = target_channel_id
        self.response_ephemeral = bool(response_ephemeral)
        super().__init__(
            habit_id=habit_id,
            habit_name=habit_name,
            user_id=user_id,
            timeout=timeout,
        )

    def button_view_kind(self) -> str:
        return "created"

    def _rebuild_items(self, *, disabled: bool = False) -> None:
        super()._rebuild_items(disabled=disabled)
        add_button = discord.ui.Button(
            label="Add Another",
            style=discord.ButtonStyle.primary,
            row=0,
            disabled=disabled,
        )
        add_button.callback = self._open_create_modal
        self.add_item(add_button)
        edit_button = discord.ui.Button(
            label="Edit Habit",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=disabled,
        )
        edit_button.callback = self._open_edit_modal
        self.add_item(edit_button)
        delete_button = discord.ui.Button(
            label="Delete",
            style=discord.ButtonStyle.danger,
            row=0,
            disabled=disabled,
        )
        delete_button.callback = self._open_delete_modal
        self.add_item(delete_button)

    async def _open_modal(
        self,
        interaction: discord.Interaction,
        *,
        modal: HabitCreateModal,
    ) -> None:
        global _MODAL_SELECTS_SUPPORTED
        if _MODAL_SELECTS_SUPPORTED:
            try:
                await interaction.response.send_modal(modal)
                return
            except discord.HTTPException as exc:
                if exc.code == 50035 and "must be one of (4,)" in str(exc):
                    _MODAL_SELECTS_SUPPORTED = False
                else:
                    raise

        modal._scope_value = str(self.scope_value or "channel")
        modal._target_channel_id = self.target_channel_id
        modal.scope_select = None
        modal.scope_select_label = None
        fallback_modal = HabitCreateModal(
            self._cog,
            user_id=self.user_id,
            scope_value=self.scope_value,
            target_channel_id=self.target_channel_id,
            response_ephemeral=self.response_ephemeral,
            guild_id=interaction.guild_id,
            channel_id=interaction.channel_id,
            include_scope_select=False,
            title=str(getattr(modal, "title", "Add Habit")),
            habit_id=getattr(modal, "_habit_id", None),
            default_habit=str(modal.habit_input.default or ""),
            default_description=str(modal.description_input.default or ""),
            default_reminder=str(modal.reminder_input.default or ""),
            source_view=getattr(modal, "_source_view", None),
            source_message=getattr(modal, "_source_message", None),
        )
        await interaction.response.send_modal(fallback_modal)

    async def _open_create_modal(self, interaction: discord.Interaction) -> None:
        self.response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=self.response_ephemeral,
        )
        self.message = interaction.message

        await self._open_modal(
            interaction,
            modal=HabitCreateModal(
                self._cog,
                user_id=interaction.user.id,
                scope_value=self.scope_value,
                target_channel_id=self.target_channel_id,
                response_ephemeral=self.response_ephemeral,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                include_scope_select=True,
            ),
        )

    async def _open_edit_modal(self, interaction: discord.Interaction) -> None:
        self.response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=self.response_ephemeral,
        )
        self.message = interaction.message

        habit = await asyncio.to_thread(
            HabitFunctions.fetch_habit,
            self.habit_id,
            interaction.guild_id,
            self.user_id,
        )
        if habit is None:
            await interaction.response.send_message(
                "That habit is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        self.habit_name = str(habit.get("name") or self.habit_name or "Habit")
        self.scope_value = HabitFunctions._normalize_scope(
            str(habit.get("scope") or self.scope_value or "channel")
        )
        self.target_channel_id = habit.get("channel_id")

        reminder_time = await asyncio.to_thread(
            HabitFunctions.get_habit_reminder_time,
            self.habit_id,
            habit.get("guild_id"),
        )

        await self._open_modal(
            interaction,
            modal=HabitCreateModal(
                self._cog,
                user_id=interaction.user.id,
                scope_value=self.scope_value,
                target_channel_id=self.target_channel_id,
                response_ephemeral=self.response_ephemeral,
                guild_id=interaction.guild_id,
                channel_id=interaction.channel_id,
                include_scope_select=True,
                title="Edit Habit",
                habit_id=self.habit_id,
                default_habit=self.habit_name,
                default_description=str(habit.get("description") or ""),
                default_reminder=_format_reminder_input(reminder_time),
                source_view=self,
                source_message=interaction.message,
            ),
        )

    async def _open_delete_modal(self, interaction: discord.Interaction) -> None:
        self.response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=self.response_ephemeral,
        )
        self.message = interaction.message

        await interaction.response.send_modal(
            HabitDeleteConfirmModal(
                self,
                source_message=interaction.message,
            )
        )

    async def _confirm_delete(
        self,
        interaction: discord.Interaction,
        *,
        source_message: Optional[discord.Message] = None,
    ) -> None:
        await interaction.response.defer(ephemeral=self.response_ephemeral)
        try:
            deleted = await asyncio.to_thread(
                HabitFunctions.delete_habit,
                self.habit_id,
                interaction.guild_id,
                self.user_id,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )
            return

        if not deleted:
            await interaction.followup.send(
                "That habit is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        deleted_payload = HabitEmbeds.deleted_habit_embed(self.habit_name)
        if source_message is not None:
            try:
                await source_message.edit(view=None, **deleted_payload)
                self.message = source_message
                return
            except discord.NotFound:
                pass
            except Exception:
                await interaction.followup.send(
                    "Habit deleted, but updating the card failed.",
                    ephemeral=self.response_ephemeral,
                )
                return

        await interaction.followup.send(
            ephemeral=self.response_ephemeral,
            **deleted_payload,
        )
