import asyncio

import discord
from discord.ext import commands
from discord.utils import MISSING

from classes.HabitFunctions import HabitFunctions
from services.visibility import inherit_ephemeral_from_interaction

_BASIC_VIEW_KIND = "basic"
_CREATED_VIEW_KIND = "created"


async def register_habit_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        HabitCompleteButton,
        HabitSkipButton,
        HabitEditButton,
        HabitDuplicateButton,
        HabitDeleteButton,
    )


def _normalize_view_kind(value: str) -> str:
    if str(value or "").strip().lower() == _CREATED_VIEW_KIND:
        return _CREATED_VIEW_KIND
    return _BASIC_VIEW_KIND


async def _build_habit_view(
    interaction: discord.Interaction,
    *,
    habit_id: str,
    user_id: int,
    view_kind: str,
    response_ephemeral: bool,
):
    from views.HabitActionView import HabitActionView
    from views.HabitCreateModal import HabitCreatedActionView

    habit = await asyncio.to_thread(
        HabitFunctions.fetch_habit,
        habit_id,
        interaction.guild_id,
        user_id,
    )
    habit_name = str((habit or {}).get("name") or "Habit")
    normalized_view_kind = _normalize_view_kind(view_kind)

    if normalized_view_kind == _CREATED_VIEW_KIND:
        habit_cog = interaction.client.get_cog("HabitCog")
        if habit_cog is not None:
            scope_value = HabitFunctions._normalize_scope(
                str((habit or {}).get("scope") or "channel")
            )
            target_channel_id = (habit or {}).get("channel_id")
            view = HabitCreatedActionView(
                habit_cog,
                habit_id=habit_id,
                habit_name=habit_name,
                user_id=user_id,
                scope_value=scope_value,
                target_channel_id=target_channel_id,
                response_ephemeral=response_ephemeral,
                today_status=HabitFunctions.today_status(habit or {}),
            )
            return view, habit

    view = HabitActionView(
        habit_id,
        habit_name,
        user_id,
        today_status=HabitFunctions.today_status(habit or {}),
    )
    return view, habit


async def _refresh_habit_message(
    interaction: discord.Interaction,
    *,
    habit_id: str,
    user_id: int,
    view_kind: str,
    response_ephemeral: bool,
) -> bool:
    view, habit = await _build_habit_view(
        interaction,
        habit_id=habit_id,
        user_id=user_id,
        view_kind=view_kind,
        response_ephemeral=response_ephemeral,
    )
    view.message = interaction.message
    return await view.refresh_message(
        interaction,
        source_message=interaction.message,
        habit=habit,
        content=MISSING,
    )


async def _record_completion(
    interaction: discord.Interaction,
    *,
    habit_id: str,
    user_id: int,
    mode: str,
    view_kind: str,
    response_ephemeral: bool,
) -> None:
    await interaction.response.defer(ephemeral=response_ephemeral)
    current_habit = await asyncio.to_thread(
        HabitFunctions.fetch_habit,
        habit_id,
        interaction.guild_id,
        interaction.user.id,
    )
    if current_habit is None:
        await interaction.followup.send(
            ephemeral=response_ephemeral,
            content="That habit is no longer available.",
        )
        return
    if HabitFunctions.today_status(current_habit) == mode:
        refreshed = await _refresh_habit_message(
            interaction,
            habit_id=habit_id,
            user_id=user_id,
            view_kind=view_kind,
            response_ephemeral=response_ephemeral,
        )
        if refreshed:
            return
        await interaction.followup.send(
            ephemeral=response_ephemeral,
            content="That habit is already set to that status for today.",
        )
        return

    updated = await asyncio.to_thread(
        HabitFunctions.add_completion,
        habit_id,
        interaction.guild_id,
        mode,
        interaction.user.id,
    )
    if not updated:
        await interaction.followup.send(
            ephemeral=response_ephemeral,
            content="Couldn't update that habit.",
        )
        return

    refreshed = await _refresh_habit_message(
        interaction,
        habit_id=habit_id,
        user_id=user_id,
        view_kind=view_kind,
        response_ephemeral=response_ephemeral,
    )
    if refreshed:
        return

    await interaction.followup.send(
        ephemeral=response_ephemeral,
        content="Updated the habit, but refreshing the card failed.",
    )


async def _run_created_habit_action(
    interaction: discord.Interaction,
    *,
    habit_id: str,
    user_id: int,
    action: str,
) -> None:
    response_ephemeral = inherit_ephemeral_from_interaction(
        interaction,
        default=True,
    )
    view, habit = await _build_habit_view(
        interaction,
        habit_id=habit_id,
        user_id=user_id,
        view_kind=_CREATED_VIEW_KIND,
        response_ephemeral=response_ephemeral,
    )
    if habit is None:
        await interaction.response.send_message(
            "That habit is no longer available.",
            ephemeral=response_ephemeral,
        )
        return

    callback = getattr(view, f"_open_{action}_modal", None)
    if callback is None:
        await interaction.response.send_message(
            "Habit actions are not available right now.",
            ephemeral=response_ephemeral,
        )
        return
    await callback(interaction)


def _created_habit_button(
    *,
    action: str,
    habit_id: str,
    user_id: int,
    emoji: str,
    style: discord.ButtonStyle,
    disabled: bool,
) -> discord.ui.Button:
    return discord.ui.Button(
        emoji=emoji,
        style=style,
        row=0,
        custom_id=f"habit:{action}:{habit_id}:{user_id}",
        disabled=disabled,
    )


class HabitCompleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"habit:complete:(?P<habit_id>[^:]+):(?P<user_id>\d+)"
        r"(?::(?P<view_kind>[a-z_]+))?"
    ),
):
    def __init__(
        self,
        habit_id: str,
        user_id: int,
        *,
        view_kind: str = _BASIC_VIEW_KIND,
        disabled: bool = False,
    ) -> None:
        self.view_kind = _normalize_view_kind(view_kind)
        super().__init__(
            discord.ui.Button(
                emoji="\N{WHITE HEAVY CHECK MARK}",
                style=discord.ButtonStyle.success,
                custom_id=f"habit:complete:{habit_id}:{user_id}:{self.view_kind}",
                disabled=disabled,
            )
        )
        self.habit_id = habit_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "HabitCompleteButton":
        del interaction
        return cls(
            match.group("habit_id"),
            int(match.group("user_id")),
            view_kind=match.group("view_kind") or _BASIC_VIEW_KIND,
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=True,
        )
        await _record_completion(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            mode="complete",
            view_kind=self.view_kind,
            response_ephemeral=response_ephemeral,
        )


class HabitSkipButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"habit:skip:(?P<habit_id>[^:]+):(?P<user_id>\d+)"
        r"(?::(?P<view_kind>[a-z_]+))?"
    ),
):
    def __init__(
        self,
        habit_id: str,
        user_id: int,
        *,
        view_kind: str = _BASIC_VIEW_KIND,
        disabled: bool = False,
    ) -> None:
        self.view_kind = _normalize_view_kind(view_kind)
        super().__init__(
            discord.ui.Button(
                emoji="\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}\N{VARIATION SELECTOR-16}",
                style=discord.ButtonStyle.secondary,
                custom_id=f"habit:skip:{habit_id}:{user_id}:{self.view_kind}",
                disabled=disabled,
            )
        )
        self.habit_id = habit_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "HabitSkipButton":
        del interaction
        return cls(
            match.group("habit_id"),
            int(match.group("user_id")),
            view_kind=match.group("view_kind") or _BASIC_VIEW_KIND,
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=True,
        )
        await _record_completion(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            mode="skip",
            view_kind=self.view_kind,
            response_ephemeral=response_ephemeral,
        )


class HabitEditButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habit:edit:(?P<habit_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(self, habit_id: str, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            _created_habit_button(
                action="edit",
                habit_id=habit_id,
                user_id=user_id,
                emoji="\N{PENCIL}\N{VARIATION SELECTOR-16}",
                style=discord.ButtonStyle.secondary,
                disabled=disabled,
            )
        )
        self.habit_id = habit_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "HabitEditButton":
        del interaction
        return cls(
            match.group("habit_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await _run_created_habit_action(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            action="edit",
        )


class HabitDuplicateButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habit:duplicate:(?P<habit_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(self, habit_id: str, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            _created_habit_button(
                action="duplicate",
                habit_id=habit_id,
                user_id=user_id,
                emoji="\N{PAGE FACING UP}",
                style=discord.ButtonStyle.primary,
                disabled=disabled,
            )
        )
        self.habit_id = habit_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "HabitDuplicateButton":
        del interaction
        return cls(
            match.group("habit_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await _run_created_habit_action(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            action="duplicate",
        )


class HabitDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habit:delete:(?P<habit_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(self, habit_id: str, user_id: int, *, disabled: bool = False) -> None:
        super().__init__(
            _created_habit_button(
                action="delete",
                habit_id=habit_id,
                user_id=user_id,
                emoji="\N{WASTEBASKET}\N{VARIATION SELECTOR-16}",
                style=discord.ButtonStyle.danger,
                disabled=disabled,
            )
        )
        self.habit_id = habit_id
        self.user_id = user_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "HabitDeleteButton":
        del interaction
        return cls(
            match.group("habit_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await _run_created_habit_action(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            action="delete",
        )
