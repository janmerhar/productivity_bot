import asyncio
from typing import Optional

import discord
from discord.ext import commands

from classes.ReminderFunctions import ReminderFunctions
from services.error_reporting import ValidationError, handle_interaction_error
from services.reminder_destination import build_reminder_destination_select_options


async def register_reminder_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        ReminderAddButton,
        ReminderEditButton,
        ReminderPingButton,
        ReminderToggleButton,
        ReminderDeleteButton,
        ReminderListItemButton,
        ReminderListPrevButton,
        ReminderListNextButton,
        ReminderListAddButton,
        ReminderListOptionsButton,
    )


def _bool_flag(value: bool) -> str:
    return "1" if value else "0"


def _parse_bool_flag(value: str) -> bool:
    return str(value or "").strip() == "1"


async def _build_output_view(
    interaction: discord.Interaction,
    *,
    job_id: str,
    user_id: int,
    response_ephemeral: bool,
    result_message: Optional[str] = None,
    ok: Optional[bool] = None,
):
    from views.ReminderOutputView import ReminderOutputView

    job = await asyncio.to_thread(
        ReminderFunctions.get_reminder,
        job_id,
        interaction.guild_id,
    )
    if result_message is None:
        result_message = (
            f"Showing reminder `{job_id}`."
            if job is not None
            else "This reminder is no longer available."
        )
    if ok is None:
        ok = job is not None

    view = ReminderOutputView(
        job=job,
        guild=interaction.guild,
        result_message=result_message,
        ok=ok,
        user_id=user_id or None,
        response_ephemeral=response_ephemeral,
        job_id=job_id,
        guild_id=interaction.guild_id,
        channel_id=interaction.channel_id,
    )
    view.message = interaction.message
    return view


async def _ensure_allowed(
    interaction: discord.Interaction,
    *,
    user_id: int,
    response_ephemeral: bool,
) -> bool:
    if user_id == 0 or interaction.user.id == user_id:
        return True

    await interaction.response.send_message(
        "Only the user who opened this reminder can manage it.",
        ephemeral=response_ephemeral,
    )
    return False


async def _build_list_view(
    interaction: discord.Interaction,
    *,
    session_id: str,
):
    from views.ReminderListView import ReminderListView

    return await ReminderListView.from_session(interaction, session_id)


async def _ensure_list_view(
    interaction: discord.Interaction,
    *,
    session_id: str,
):
    view = await _build_list_view(
        interaction,
        session_id=session_id,
    )
    if view is None:
        await interaction.response.send_message(
            "That reminder list is no longer available. Run `/reminder list` again.",
            ephemeral=True,
        )
        return None

    if not await view.interaction_check(interaction):
        return None

    return view


class ReminderAddButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:add:(?P<job_id>[^:]+):(?P<user_id>\d+):(?P<ephemeral>[01])",
):
    def __init__(
        self,
        job_id: str,
        user_id: int,
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="➕",
                style=discord.ButtonStyle.success,
                row=0,
                custom_id=(
                    f"reminder:add:{job_id}:{user_id}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.user_id = user_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderAddButton":
        del interaction
        return cls(
            match.group("job_id"),
            int(match.group("user_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.ReminderEditModal import ReminderCreateModal

        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        parent_view = await _build_output_view(
            interaction,
            job_id=self.job_id,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        )
        default_channel_id = parent_view.channel_id or interaction.channel_id
        default_destination_type = (
            "private"
            if parent_view.job is not None
            and ReminderFunctions.is_private_destination(parent_view.job)
            else "channel"
        )
        await interaction.response.send_modal(
            ReminderCreateModal(
                parent_view=parent_view,
                default_channel_id=default_channel_id,
                default_destination_type=default_destination_type,
                guild=interaction.guild or parent_view.guild,
                source_message=interaction.message,
                response_ephemeral=self.response_ephemeral,
                guild_id=interaction.guild_id,
            )
        )


class ReminderEditButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:edit:(?P<job_id>[^:]+):(?P<user_id>\d+):(?P<ephemeral>[01])",
):
    def __init__(
        self,
        job_id: str,
        user_id: int,
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="✏️",
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=(
                    f"reminder:edit:{job_id}:{user_id}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.user_id = user_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderEditButton":
        del interaction
        return cls(
            match.group("job_id"),
            int(match.group("user_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.ReminderEditModal import ReminderEditModal

        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        parent_view = await _build_output_view(
            interaction,
            job_id=self.job_id,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        )
        if parent_view.job is None:
            await interaction.response.send_message(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        channel_options = build_reminder_destination_select_options(
            interaction.guild,
            parent_view.job.channel_id,
            is_private_selected=ReminderFunctions.is_private_destination(parent_view.job),
        )
        await interaction.response.send_modal(
            ReminderEditModal(
                parent_view.job,
                channel_options=channel_options,
                parent_view=parent_view,
                source_message=interaction.message,
                response_ephemeral=self.response_ephemeral,
            )
        )


class ReminderPingButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:ping:(?P<job_id>[^:]+):(?P<user_id>\d+):(?P<ephemeral>[01])",
):
    def __init__(
        self,
        job_id: str,
        user_id: int,
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="🔔",
                style=discord.ButtonStyle.primary,
                row=0,
                custom_id=(
                    f"reminder:ping:{job_id}:{user_id}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.user_id = user_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderPingButton":
        del interaction
        return cls(
            match.group("job_id"),
            int(match.group("user_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.ReminderEditModal import ReminderPingModal

        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        parent_view = await _build_output_view(
            interaction,
            job_id=self.job_id,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        )
        if parent_view.job is None:
            await interaction.response.send_message(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        await interaction.response.send_modal(
            ReminderPingModal(
                guild=interaction.guild or parent_view.guild,
                guild_id=parent_view.guild_id,
                default_channel_id=parent_view.channel_id or interaction.channel_id,
                response_ephemeral=self.response_ephemeral,
                user_id=interaction.user.id,
                job=parent_view.job,
                parent_view=parent_view,
                source_message=interaction.message,
            )
        )


class ReminderToggleButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:toggle:(?P<job_id>[^:]+):(?P<user_id>\d+):(?P<ephemeral>[01])",
):
    def __init__(
        self,
        job_id: str,
        user_id: int,
        response_ephemeral: bool,
        *,
        paused: bool = False,
        disabled: bool = False,
    ) -> None:
        emoji = "▶️" if paused else "⏸️"
        style = discord.ButtonStyle.success if paused else discord.ButtonStyle.secondary
        if disabled:
            emoji = "🚫"
            style = discord.ButtonStyle.secondary

        super().__init__(
            discord.ui.Button(
                emoji=emoji,
                style=style,
                row=0,
                custom_id=(
                    f"reminder:toggle:{job_id}:{user_id}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.user_id = user_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderToggleButton":
        del interaction
        emoji = getattr(item, "emoji", None)
        emoji_value = str(emoji) if emoji is not None else ""
        return cls(
            match.group("job_id"),
            int(match.group("user_id")),
            _parse_bool_flag(match.group("ephemeral")),
            paused=emoji_value == "▶️",
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        parent_view = await _build_output_view(
            interaction,
            job_id=self.job_id,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        )
        if parent_view.job is None:
            parent_view.result_message = "This reminder is no longer available."
            parent_view.ok = False
            await interaction.response.edit_message(**parent_view.response_payload())
            return

        await interaction.response.defer(ephemeral=self.response_ephemeral)

        try:
            if ReminderFunctions.is_paused(parent_view.job):
                result = await asyncio.to_thread(
                    ReminderFunctions.resume_reminder,
                    self.job_id,
                    parent_view.guild_id,
                )
                desired_message = f"Resumed reminder `{self.job_id}`."
                no_change_message = f"Reminder `{self.job_id}` is already active."
            else:
                result = await asyncio.to_thread(
                    ReminderFunctions.pause_reminder,
                    self.job_id,
                    parent_view.guild_id,
                )
                desired_message = f"Paused reminder `{self.job_id}`."
                no_change_message = f"Reminder `{self.job_id}` is already paused."
        except ValueError as exc:
            await handle_interaction_error(
                interaction,
                ValidationError(
                    "That reminder ID is invalid.",
                    ephemeral=self.response_ephemeral,
                    cause=exc,
                ),
                ephemeral=self.response_ephemeral,
            )
            return
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )
            return

        if result == "missing":
            parent_view.result_message = "This reminder is no longer available."
            parent_view.ok = False
            await parent_view.refresh_message(
                interaction,
                source_message=interaction.message,
                result_message=parent_view.result_message,
            )
            return

        result_message = no_change_message if "already_" in result else desired_message
        parent_view.ok = True
        await parent_view.refresh_message(
            interaction,
            source_message=interaction.message,
            result_message=result_message,
        )


class ReminderDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:delete:(?P<job_id>[^:]+):(?P<user_id>\d+):(?P<ephemeral>[01])",
):
    def __init__(
        self,
        job_id: str,
        user_id: int,
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="🗑️",
                style=discord.ButtonStyle.danger,
                row=0,
                custom_id=(
                    f"reminder:delete:{job_id}:{user_id}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.user_id = user_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderDeleteButton":
        del interaction
        return cls(
            match.group("job_id"),
            int(match.group("user_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.ReminderOutputView import ReminderDeleteConfirmModal

        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        ):
            return

        parent_view = await _build_output_view(
            interaction,
            job_id=self.job_id,
            user_id=self.user_id,
            response_ephemeral=self.response_ephemeral,
        )
        if parent_view.job is None:
            await interaction.response.send_message(
                "That reminder is no longer available.",
                ephemeral=self.response_ephemeral,
            )
            return

        await interaction.response.send_modal(ReminderDeleteConfirmModal(parent_view))


class ReminderListItemButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:list:item:(?P<session_id>[0-9a-f]{16}):(?P<slot>[1-5])",
):
    def __init__(
        self,
        session_id: str,
        slot: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label=str(slot),
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=f"reminder:list:item:{session_id}:{slot}",
                disabled=disabled,
            )
        )
        self.session_id = session_id
        self.slot = slot

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderListItemButton":
        del interaction
        return cls(
            match.group("session_id"),
            int(match.group("slot")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_list_view(
            interaction,
            session_id=self.session_id,
        )
        if view is None:
            return

        await view._open_reminder_details(
            interaction,
            view._page_item(self.slot - 1),
        )


class ReminderListPrevButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:list:prev:(?P<session_id>[0-9a-f]{16})",
):
    def __init__(
        self,
        session_id: str,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
                style=discord.ButtonStyle.secondary,
                row=1,
                custom_id=f"reminder:list:prev:{session_id}",
                disabled=disabled,
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderListPrevButton":
        del interaction
        return cls(
            match.group("session_id"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_list_view(
            interaction,
            session_id=self.session_id,
        )
        if view is None:
            return

        if view.page <= 1:
            await interaction.response.defer(ephemeral=True)
            return

        view.page -= 1
        view._build()
        await view.save_session()
        await interaction.response.edit_message(view=view, **view.payload())


class ReminderListNextButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:list:next:(?P<session_id>[0-9a-f]{16})",
):
    def __init__(
        self,
        session_id: str,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}",
                style=discord.ButtonStyle.secondary,
                row=1,
                custom_id=f"reminder:list:next:{session_id}",
                disabled=disabled,
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderListNextButton":
        del interaction
        return cls(
            match.group("session_id"),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_list_view(
            interaction,
            session_id=self.session_id,
        )
        if view is None:
            return

        if view.page >= view.total_pages:
            await interaction.response.defer(ephemeral=True)
            return

        view.page += 1
        view._build()
        await view.save_session()
        await interaction.response.edit_message(view=view, **view.payload())


class ReminderListAddButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:list:add:(?P<session_id>[0-9a-f]{16})",
):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\N{HEAVY PLUS SIGN}",
                style=discord.ButtonStyle.success,
                row=1,
                custom_id=f"reminder:list:add:{session_id}",
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderListAddButton":
        del interaction, item
        return cls(match.group("session_id"))

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_list_view(
            interaction,
            session_id=self.session_id,
        )
        if view is None:
            return

        await view.open_create_modal(
            interaction,
            source_message=interaction.message,
        )


class ReminderListOptionsButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"reminder:list:options:(?P<session_id>[0-9a-f]{16})",
):
    def __init__(
        self,
        session_id: str,
        *,
        active: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\N{RIGHT-POINTING MAGNIFYING GLASS}",
                style=(
                    discord.ButtonStyle.success
                    if active
                    else discord.ButtonStyle.secondary
                ),
                row=1,
                custom_id=f"reminder:list:options:{session_id}",
            )
        )
        self.session_id = session_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ReminderListOptionsButton":
        del interaction
        return cls(
            match.group("session_id"),
            active=getattr(item, "style", None) == discord.ButtonStyle.success,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _ensure_list_view(
            interaction,
            session_id=self.session_id,
        )
        if view is None:
            return

        await view.open_options_modal(
            interaction,
            source_message=interaction.message,
        )
