import asyncio

import discord
from discord.ext import commands

from classes.HabitFunctions import HabitFunctions
from services.visibility import inherit_ephemeral_from_interaction

_BASIC_VIEW_KIND = "basic"
_CREATED_VIEW_KIND = "created"


async def register_habit_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        HabitCompleteButton,
        HabitSkipButton,
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
            )
            return view, habit

    view = HabitActionView(habit_id, habit_name, user_id)
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
                label="complete",
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
                label="skip",
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
