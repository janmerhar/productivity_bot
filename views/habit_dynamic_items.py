import asyncio

import discord
from discord.ext import commands

from classes.HabitFunctions import HabitFunctions
from services.visibility import inherit_ephemeral_from_interaction


async def register_habit_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        HabitCompleteButton,
        HabitSkipButton,
        HabitIncompleteButton,
    )


async def _ensure_allowed(
    interaction: discord.Interaction,
    *,
    user_id: int,
    response_ephemeral: bool,
) -> bool:
    if interaction.user.id == user_id:
        return True

    await interaction.response.send_message(
        ephemeral=response_ephemeral,
        content="Only the habit owner can update this habit.",
    )
    return False


async def _refresh_habit_message(
    interaction: discord.Interaction,
    *,
    habit_id: str,
    user_id: int,
) -> None:
    from views.HabitActionView import HabitActionView

    view = HabitActionView(habit_id, "Habit", user_id)
    await view.refresh_message(interaction)


async def _record_completion(
    interaction: discord.Interaction,
    *,
    habit_id: str,
    user_id: int,
    mode: str,
    response_ephemeral: bool,
) -> None:
    await interaction.response.defer(ephemeral=response_ephemeral)
    updated = await asyncio.to_thread(
        HabitFunctions.add_completion,
        habit_id,
        interaction.guild_id,
        mode,
    )
    if not updated:
        await interaction.followup.send(
            ephemeral=response_ephemeral,
            content="Couldn't update that habit.",
        )
        return

    await _refresh_habit_message(
        interaction,
        habit_id=habit_id,
        user_id=user_id,
    )
    habit = await asyncio.to_thread(
        HabitFunctions.fetch_habit,
        habit_id,
        interaction.guild_id,
    )
    habit_name = str((habit or {}).get("name") or "Habit")
    await interaction.followup.send(
        ephemeral=response_ephemeral,
        content=f"Marked '{habit_name}' as {mode}.",
    )


class HabitCompleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habit:complete:(?P<habit_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        habit_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="complete",
                style=discord.ButtonStyle.success,
                custom_id=f"habit:complete:{habit_id}:{user_id}",
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
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=True,
        )
        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        await _record_completion(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            mode="complete",
            response_ephemeral=response_ephemeral,
        )


class HabitSkipButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habit:skip:(?P<habit_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        habit_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="skip",
                style=discord.ButtonStyle.secondary,
                custom_id=f"habit:skip:{habit_id}:{user_id}",
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
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=True,
        )
        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        await _record_completion(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            mode="skip",
            response_ephemeral=response_ephemeral,
        )


class HabitIncompleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"habit:incomplete:(?P<habit_id>[^:]+):(?P<user_id>\d+)",
):
    def __init__(
        self,
        habit_id: str,
        user_id: int,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="incomplete",
                style=discord.ButtonStyle.danger,
                custom_id=f"habit:incomplete:{habit_id}:{user_id}",
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
    ) -> "HabitIncompleteButton":
        del interaction
        return cls(
            match.group("habit_id"),
            int(match.group("user_id")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        response_ephemeral = inherit_ephemeral_from_interaction(
            interaction,
            default=True,
        )
        if not await _ensure_allowed(
            interaction,
            user_id=self.user_id,
            response_ephemeral=response_ephemeral,
        ):
            return

        await _record_completion(
            interaction,
            habit_id=self.habit_id,
            user_id=self.user_id,
            mode="incomplete",
            response_ephemeral=response_ephemeral,
        )
