import asyncio
from typing import Optional

import discord
from discord.ext import commands

from classes.DailyJobManager import DailyJobManager
from embeds.DailyTaskEmbeds import DailyTaskEmbeds
from services.discord_helpers import resolve_messageable_channel
from services.error_reporting import ValidationError, handle_interaction_error

_MODAL_SELECTS_SUPPORTED = True


async def register_scheduled_job_dynamic_items(bot: commands.Bot) -> None:
    bot.add_dynamic_items(
        ScheduledJobRunNowButton,
        ScheduledJobEditButton,
        ScheduledJobChangeChannelButton,
        ScheduledJobDeleteButton,
    )


def _int_value(value: Optional[int]) -> int:
    return int(value or 0)


def _parse_optional_int(raw_value: str) -> Optional[int]:
    parsed = int(raw_value)
    return parsed or None


def _bool_flag(value: bool) -> str:
    return "1" if value else "0"


def _parse_bool_flag(value: str) -> bool:
    return str(value or "").strip() == "1"


async def _build_view(
    interaction: discord.Interaction,
    *,
    job_id: str,
    channel_id: Optional[int],
    guild_id: Optional[int],
    response_ephemeral: bool,
):
    from views.ScheduledJobActionView import ScheduledJobActionView

    view = ScheduledJobActionView(
        job_id=job_id,
        channel_id=channel_id,
        guild_id=guild_id,
        response_ephemeral=response_ephemeral,
    )
    view.message = interaction.message
    await view.load_job()
    return view


class ScheduledJobRunNowButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"job:run:(?P<job_id>[^:]+):(?P<channel_id>\d+):"
        r"(?P<guild_id>\d+):(?P<ephemeral>[01])"
    ),
):
    def __init__(
        self,
        job_id: str,
        channel_id: Optional[int],
        guild_id: Optional[int],
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Run now",
                style=discord.ButtonStyle.success,
                custom_id=(
                    f"job:run:{job_id}:{_int_value(channel_id)}:"
                    f"{_int_value(guild_id)}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ScheduledJobRunNowButton":
        del interaction
        return cls(
            match.group("job_id"),
            _parse_optional_int(match.group("channel_id")),
            _parse_optional_int(match.group("guild_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=self.response_ephemeral)

        try:
            view = await _build_view(
                interaction,
                job_id=self.job_id,
                channel_id=self.channel_id,
                guild_id=self.guild_id,
                response_ephemeral=self.response_ephemeral,
            )
            job = view.job
            if job is None:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=self.response_ephemeral,
                )

            if job.type not in {"message", "crypto", "stock"}:
                raise ValidationError(
                    "Run now is currently supported for message, crypto, and stock jobs.",
                    ephemeral=self.response_ephemeral,
                )

            payload = await asyncio.to_thread(job.run)
            if not payload:
                raise ValidationError(
                    "This job did not produce any output to send.",
                    ephemeral=self.response_ephemeral,
                )

            bot = interaction.client
            if not isinstance(bot, commands.Bot):
                raise ValidationError(
                    "Bot is not ready to send this job.",
                    ephemeral=self.response_ephemeral,
                )

            channel = await resolve_messageable_channel(bot, job.channel_id)
            if channel is None:
                raise ValidationError(
                    "I can't access the destination channel for this job.",
                    ephemeral=self.response_ephemeral,
                )

            await channel.send(**payload)
            await interaction.followup.send(
                f"Ran job `{self.job_id}` now in <#{job.channel_id}>.",
                ephemeral=self.response_ephemeral,
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )


class ScheduledJobEditButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"job:edit:(?P<job_id>[^:]+):(?P<channel_id>\d+):"
        r"(?P<guild_id>\d+):(?P<ephemeral>[01])"
    ),
):
    def __init__(
        self,
        job_id: str,
        channel_id: Optional[int],
        guild_id: Optional[int],
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.secondary,
                custom_id=(
                    f"job:edit:{job_id}:{_int_value(channel_id)}:"
                    f"{_int_value(guild_id)}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ScheduledJobEditButton":
        del interaction
        return cls(
            match.group("job_id"),
            _parse_optional_int(match.group("channel_id")),
            _parse_optional_int(match.group("guild_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        from views.ScheduledJobActionView import ScheduledJobEditModal

        try:
            view = await _build_view(
                interaction,
                job_id=self.job_id,
                channel_id=self.channel_id,
                guild_id=self.guild_id,
                response_ephemeral=self.response_ephemeral,
            )
            job = view.job
            if job is None:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=self.response_ephemeral,
                )
            if job.type not in {"message", "crypto", "stock"}:
                raise ValidationError(
                    "Editing is currently supported for message, crypto, and stock jobs.",
                    ephemeral=self.response_ephemeral,
                )

            await interaction.response.send_modal(
                ScheduledJobEditModal(
                    view,
                    job,
                    source_message=interaction.message,
                )
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )


class ScheduledJobChangeChannelButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"job:channel:(?P<job_id>[^:]+):(?P<channel_id>\d+):"
        r"(?P<guild_id>\d+):(?P<ephemeral>[01])"
    ),
):
    def __init__(
        self,
        job_id: str,
        channel_id: Optional[int],
        guild_id: Optional[int],
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Change Channel",
                style=discord.ButtonStyle.primary,
                custom_id=(
                    f"job:channel:{job_id}:{_int_value(channel_id)}:"
                    f"{_int_value(guild_id)}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ScheduledJobChangeChannelButton":
        del interaction
        return cls(
            match.group("job_id"),
            _parse_optional_int(match.group("channel_id")),
            _parse_optional_int(match.group("guild_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        global _MODAL_SELECTS_SUPPORTED

        from views.ScheduledJobActionView import (
            ScheduledJobChangeChannelModal,
            _build_channel_select_options,
        )

        try:
            view = await _build_view(
                interaction,
                job_id=self.job_id,
                channel_id=self.channel_id,
                guild_id=self.guild_id,
                response_ephemeral=self.response_ephemeral,
            )
            if view.job is None:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=self.response_ephemeral,
                )

            channel_options = _build_channel_select_options(
                interaction,
                view.channel_id,
            )
            if _MODAL_SELECTS_SUPPORTED:
                try:
                    await interaction.response.send_modal(
                        ScheduledJobChangeChannelModal(
                            view,
                            channel_options=channel_options,
                        )
                    )
                    return
                except discord.HTTPException as exc:
                    if exc.code == 50035 and "must be one of (4,)" in str(exc):
                        _MODAL_SELECTS_SUPPORTED = False
                    else:
                        raise

            await interaction.response.send_modal(ScheduledJobChangeChannelModal(view))
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )


class ScheduledJobDeleteButton(
    discord.ui.DynamicItem[discord.ui.Button],
    template=(
        r"job:delete:(?P<job_id>[^:]+):(?P<channel_id>\d+):"
        r"(?P<guild_id>\d+):(?P<ephemeral>[01])"
    ),
):
    def __init__(
        self,
        job_id: str,
        channel_id: Optional[int],
        guild_id: Optional[int],
        response_ephemeral: bool,
        *,
        disabled: bool = False,
    ) -> None:
        super().__init__(
            discord.ui.Button(
                label="Delete",
                style=discord.ButtonStyle.danger,
                custom_id=(
                    f"job:delete:{job_id}:{_int_value(channel_id)}:"
                    f"{_int_value(guild_id)}:{_bool_flag(response_ephemeral)}"
                ),
                disabled=disabled,
            )
        )
        self.job_id = job_id
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.response_ephemeral = response_ephemeral

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item,
        match,
        /,
    ) -> "ScheduledJobDeleteButton":
        del interaction
        return cls(
            match.group("job_id"),
            _parse_optional_int(match.group("channel_id")),
            _parse_optional_int(match.group("guild_id")),
            _parse_bool_flag(match.group("ephemeral")),
            disabled=getattr(item, "disabled", False),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        manager = DailyJobManager()
        try:
            view = await _build_view(
                interaction,
                job_id=self.job_id,
                channel_id=self.channel_id,
                guild_id=self.guild_id,
                response_ephemeral=self.response_ephemeral,
            )
            deleted = await asyncio.to_thread(
                manager.delete_job,
                self.job_id,
                self.channel_id,
                self.guild_id,
            )
            if not deleted:
                raise ValidationError(
                    "That job no longer exists in this channel.",
                    ephemeral=self.response_ephemeral,
                )

            view._rebuild_items(disabled=True)
            await view.refresh_message()

            await interaction.followup.send(
                ephemeral=False,
                **DailyTaskEmbeds.jobs_cancel_embed(
                    f"Deleted job `{self.job_id}`.",
                    ok=True,
                ),
            )
        except Exception as exc:
            await handle_interaction_error(
                interaction,
                exc,
                ephemeral=self.response_ephemeral,
            )
