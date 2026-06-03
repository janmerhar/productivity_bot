import asyncio
from typing import Optional

import discord
from discord.ext import commands
from services.visibility import inherit_ephemeral_from_interaction


async def register_toggl_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        TogglPlayPauseButton,
        TogglStopButton,
        TogglEditButton,
        TogglDeleteButton,
        TogglListTimersButton,
        TogglTimerHistoryButton,
    )


def _decode_optional_int(value: str) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed or None


def _history_sort_value(sort: str) -> str:
    return "a" if sort == "ascending" else "d"


def _history_sort_label(value: str) -> str:
    return "ascending" if value == "a" else "descending"


async def _send_history_error(
    interaction: discord.Interaction,
    message: str,
    *,
    response_ephemeral: bool,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(
            ephemeral=response_ephemeral,
            content=message,
        )
        return
    await interaction.response.send_message(
        ephemeral=response_ephemeral,
        content=message,
    )


async def _build_history_view(
    interaction: discord.Interaction,
    *,
    guild_id: Optional[int],
    user_id: int,
    page: int,
    sort: str,
    response_ephemeral: bool,
):
    from views.TogglTimerHistoryView import TogglTimerHistoryView

    if interaction.user.id != user_id:
        await _send_history_error(
            interaction,
            "Only the user who opened this Toggl timer list can manage it.",
            response_ephemeral=response_ephemeral,
        )
        return None

    try:
        view = await TogglTimerHistoryView.from_dynamic_reference(
            guild_id=guild_id,
            user_id=user_id,
            page=page,
            sort=sort,
            response_ephemeral=response_ephemeral,
        )
    except Exception:
        await _send_history_error(
            interaction,
            "I couldn't load your recent Toggl timers right now. Please try again.",
            response_ephemeral=response_ephemeral,
        )
        return None

    if view is None:
        await _send_history_error(
            interaction,
            "Your Toggl API key is missing.",
            response_ephemeral=response_ephemeral,
        )
        return None
    return view


async def _build_view(
    interaction: discord.Interaction,
    *,
    guild_id: Optional[int],
    user_id: int,
    workspace_id: Optional[int],
    time_entry_id: Optional[int],
    is_active_hint: bool,
):
    from views.TogglTimerView import TogglTimerView

    if interaction.user.id != user_id:
        await interaction.response.send_message(
            ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
            content="Only the user who opened this Toggl timer can manage it.",
        )
        return None

    view = await TogglTimerView.from_dynamic_reference(
        guild_id=guild_id,
        user_id=user_id,
        workspace_id=workspace_id,
        time_entry_id=time_entry_id,
        is_active_hint=is_active_hint,
        response_ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
    )
    if view is None:
        await interaction.response.send_message(
            ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
            content="That Toggl timer is no longer available.",
        )
        return None

    return view


class TogglPlayPauseButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"toggl:toggle:(?P<guild_id>\d+):(?P<user_id>\d+):(?P<workspace_id>\d+):(?P<time_entry_id>\d+):(?P<active>[01])",
):
    def __init__(
        self,
        *,
        guild_id: int,
        user_id: int,
        workspace_id: int,
        time_entry_id: int,
        is_active: bool,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\u23f8\ufe0f" if is_active else "\u25b6\ufe0f",
                style=(
                    discord.ButtonStyle.secondary
                    if is_active
                    else discord.ButtonStyle.success
                ),
                row=0,
                custom_id=(
                    f"toggl:toggle:{guild_id}:{user_id}:{workspace_id}:{time_entry_id}:"
                    f"{1 if is_active else 0}"
                ),
                disabled=disabled,
            )
        )
        self.guild_id = guild_id
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.time_entry_id = time_entry_id
        self.is_active = is_active

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TogglPlayPauseButton":
        del interaction
        return cls(
            guild_id=int(match.group("guild_id")),
            user_id=int(match.group("user_id")),
            workspace_id=int(match.group("workspace_id")),
            time_entry_id=int(match.group("time_entry_id")),
            is_active=match.group("active") == "1",
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _build_view(
            interaction,
            guild_id=_decode_optional_int(str(self.guild_id)),
            user_id=self.user_id,
            workspace_id=_decode_optional_int(str(self.workspace_id)),
            time_entry_id=_decode_optional_int(str(self.time_entry_id)),
            is_active_hint=self.is_active,
        )
        if view is None:
            return
        await view._handle_play_pause(interaction)


class TogglStopButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"toggl:stop:(?P<guild_id>\d+):(?P<user_id>\d+):(?P<workspace_id>\d+):(?P<time_entry_id>\d+):(?P<active>[01])",
):
    def __init__(
        self,
        *,
        guild_id: int,
        user_id: int,
        workspace_id: int,
        time_entry_id: int,
        is_active: bool,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\u23f9\ufe0f",
                style=discord.ButtonStyle.danger,
                row=0,
                custom_id=(
                    f"toggl:stop:{guild_id}:{user_id}:{workspace_id}:{time_entry_id}:"
                    f"{1 if is_active else 0}"
                ),
                disabled=disabled,
            )
        )
        self.guild_id = guild_id
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.time_entry_id = time_entry_id
        self.is_active = is_active

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TogglStopButton":
        del interaction
        return cls(
            guild_id=int(match.group("guild_id")),
            user_id=int(match.group("user_id")),
            workspace_id=int(match.group("workspace_id")),
            time_entry_id=int(match.group("time_entry_id")),
            is_active=match.group("active") == "1",
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _build_view(
            interaction,
            guild_id=_decode_optional_int(str(self.guild_id)),
            user_id=self.user_id,
            workspace_id=_decode_optional_int(str(self.workspace_id)),
            time_entry_id=_decode_optional_int(str(self.time_entry_id)),
            is_active_hint=self.is_active,
        )
        if view is None:
            return
        await view._handle_stop(interaction)


class TogglEditButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"toggl:edit:(?P<guild_id>\d+):(?P<user_id>\d+):(?P<workspace_id>\d+):(?P<time_entry_id>\d+)",
):
    def __init__(
        self,
        *,
        guild_id: int,
        user_id: int,
        workspace_id: int,
        time_entry_id: int,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\u270f\ufe0f",
                style=discord.ButtonStyle.primary,
                row=0,
                custom_id=f"toggl:edit:{guild_id}:{user_id}:{workspace_id}:{time_entry_id}",
                disabled=disabled,
            )
        )
        self.guild_id = guild_id
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.time_entry_id = time_entry_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TogglEditButton":
        del interaction
        return cls(
            guild_id=int(match.group("guild_id")),
            user_id=int(match.group("user_id")),
            workspace_id=int(match.group("workspace_id")),
            time_entry_id=int(match.group("time_entry_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _build_view(
            interaction,
            guild_id=_decode_optional_int(str(self.guild_id)),
            user_id=self.user_id,
            workspace_id=_decode_optional_int(str(self.workspace_id)),
            time_entry_id=_decode_optional_int(str(self.time_entry_id)),
            is_active_hint=False,
        )
        if view is None:
            return
        await view._handle_edit(interaction)


class TogglDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"toggl:delete:(?P<guild_id>\d+):(?P<user_id>\d+):(?P<workspace_id>\d+):(?P<time_entry_id>\d+)",
):
    def __init__(
        self,
        *,
        guild_id: int,
        user_id: int,
        workspace_id: int,
        time_entry_id: int,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\U0001f5d1\ufe0f",
                style=discord.ButtonStyle.danger,
                row=0,
                custom_id=(
                    f"toggl:delete:{guild_id}:{user_id}:{workspace_id}:{time_entry_id}"
                ),
                disabled=disabled,
            )
        )
        self.guild_id = guild_id
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.time_entry_id = time_entry_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TogglDeleteButton":
        del interaction
        return cls(
            guild_id=int(match.group("guild_id")),
            user_id=int(match.group("user_id")),
            workspace_id=int(match.group("workspace_id")),
            time_entry_id=int(match.group("time_entry_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = await _build_view(
            interaction,
            guild_id=_decode_optional_int(str(self.guild_id)),
            user_id=self.user_id,
            workspace_id=_decode_optional_int(str(self.workspace_id)),
            time_entry_id=_decode_optional_int(str(self.time_entry_id)),
            is_active_hint=False,
        )
        if view is None:
            return
        await view._handle_delete(interaction)


class TogglListTimersButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"toggl:list:(?P<guild_id>\d+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        *,
        guild_id: int,
        user_id: int,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                emoji="\U0001f4cb",
                style=discord.ButtonStyle.secondary,
                row=0,
                custom_id=f"toggl:list:{guild_id}:{user_id}",
            )
        )
        self.guild_id = guild_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TogglListTimersButton":
        del interaction, item
        return cls(
            guild_id=int(match.group("guild_id")),
            user_id=int(match.group("user_id")),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message(
                ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
                content="Only the user who opened this Toggl timer can manage it.",
            )
            return

        from embeds.TogglEmbeds import TogglEmbeds
        from views.TogglTimerHistoryView import TogglTimerHistoryView

        try:
            payload = await asyncio.to_thread(
                TogglEmbeds.timerhistory_embed,
                5,
                _decode_optional_int(str(self.guild_id)),
                self.user_id,
            )
        except Exception:
            await interaction.response.send_message(
                ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
                content="I couldn't load your recent Toggl timers right now. Please try again.",
            )
            return

        toggl_timer_history_view = payload.pop("_toggl_timer_history_view", None)
        if toggl_timer_history_view is not None:
            toggl_timer_history_view["response_ephemeral"] = (
                inherit_ephemeral_from_interaction(interaction, default=True)
            )
            payload["view"] = TogglTimerHistoryView(**toggl_timer_history_view)

        await interaction.response.send_message(
            ephemeral=inherit_ephemeral_from_interaction(interaction, default=True),
            **payload,
        )


class TogglTimerHistoryButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"togglhistory:(?P<action>info|prev|next|sort):(?P<guild_id>\d+):"
        r"(?P<user_id>\d+):(?P<page>\d+):(?P<sort>[ad])"
        r"(?::(?P<slot>[0-4]))?"
    ),
):
    def __init__(
        self,
        action: str,
        *,
        guild_id: int,
        user_id: int,
        page: int,
        sort: str,
        slot: Optional[int] = None,
        disabled: bool = False,
    ) -> None:
        if action == "info":
            if slot is None:
                raise ValueError("Toggl timer history info actions need a slot.")
            label = str(slot + 1)
            emoji = "\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16}"
            row = 0
        elif action == "prev":
            label = None
            emoji = "\N{BLACK LEFT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"
            row = 1
        elif action == "next":
            label = None
            emoji = "\N{BLACK RIGHT-POINTING TRIANGLE}\N{VARIATION SELECTOR-16}"
            row = 1
        elif action == "sort":
            label = None
            emoji = "\N{UP DOWN ARROW}\N{VARIATION SELECTOR-16}"
            row = 1
        else:
            raise ValueError(f"Unsupported Toggl history action: {action}")

        suffix = f":{slot}" if slot is not None else ""
        super().__init__(
            discord.ui.Button(
                label=label,
                emoji=emoji,
                style=discord.ButtonStyle.secondary,
                row=row,
                custom_id=(
                    f"togglhistory:{action}:{guild_id}:{user_id}:{page}:"
                    f"{_history_sort_value(sort)}{suffix}"
                ),
                disabled=disabled,
            )
        )
        self.action = action
        self.guild_id = guild_id
        self.user_id = user_id
        self.page = max(1, int(page or 1))
        self.sort = "ascending" if sort == "ascending" else "descending"
        self.slot = slot

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "TogglTimerHistoryButton":
        del interaction
        slot = match.groupdict().get("slot")
        return cls(
            match.group("action"),
            guild_id=int(match.group("guild_id")),
            user_id=int(match.group("user_id")),
            page=int(match.group("page")),
            sort=_history_sort_label(match.group("sort")),
            slot=int(slot) if slot is not None else None,
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=True,
        )
        if interaction.user.id != self.user_id:
            await _send_history_error(
                interaction,
                "Only the user who opened this Toggl timer list can manage it.",
                response_ephemeral=response_ephemeral,
            )
            return

        await interaction.response.defer(ephemeral=response_ephemeral)
        view = await _build_history_view(
            interaction,
            guild_id=_decode_optional_int(str(self.guild_id)),
            user_id=self.user_id,
            page=self.page,
            sort=self.sort,
            response_ephemeral=response_ephemeral,
        )
        if view is None:
            return

        if self.action == "info":
            await view._show_timer(interaction, int(self.slot or 0))
            return
        if self.action == "prev":
            view.page = max(1, view.page - 1)
        elif self.action == "next":
            view.page = min(view.total_pages, view.page + 1)
        elif self.action == "sort":
            view.sort = "ascending" if view.sort == "descending" else "descending"
            view.page = 1
        await view._refresh_message(interaction)
