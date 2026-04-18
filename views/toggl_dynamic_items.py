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
    )


def _decode_optional_int(value: str) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed or None


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
