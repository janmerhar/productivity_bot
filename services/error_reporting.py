import logging
import uuid
from typing import Iterable, Optional

import discord
from discord import app_commands


class UserVisibleError(Exception):
    def __init__(
        self,
        message: str,
        *,
        title: str = "Error",
        hint: Optional[str] = None,
        details: Optional[Iterable[str]] = None,
        code: Optional[str] = None,
        ephemeral: Optional[bool] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.title = title
        self.hint = hint
        self.details = list(details) if details else []
        self.code = code
        self.ephemeral = ephemeral
        self.cause = cause


class ValidationError(UserVisibleError):
    def __init__(
        self,
        message: str,
        *,
        hint: Optional[str] = None,
        details: Optional[Iterable[str]] = None,
        code: Optional[str] = None,
        ephemeral: Optional[bool] = None,
        cause: Optional[Exception] = None,
    ) -> None:
        super().__init__(
            message,
            title="Invalid input",
            hint=hint,
            details=details,
            code=code,
            ephemeral=ephemeral,
            cause=cause,
        )


def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return " ".join(parts)


def _build_error_embed(
    *,
    title: str,
    message: str,
    hint: Optional[str],
    details: Iterable[str],
    error_id: Optional[str],
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=message,
        color=discord.Colour.red(),
    )

    detail_list = [line.strip() for line in details if line and str(line).strip()]
    if detail_list:
        embed.add_field(
            name="Details",
            value="\n".join(f"- {line}" for line in detail_list),
            inline=False,
        )

    if hint:
        embed.add_field(name="Hint", value=hint, inline=False)

    if error_id:
        embed.set_footer(text=f"Error ID: {error_id}")
    return embed


def _describe_error(
    original: Exception,
    *,
    default_ephemeral: bool = True,
) -> tuple[str, str, Optional[str], list[str], bool, bool]:
    title = "Error"
    message = "Something went wrong while running that command."
    hint = None
    details: list[str] = []
    ephemeral = default_ephemeral
    is_expected = False

    if isinstance(original, UserVisibleError):
        title = original.title
        message = original.message
        hint = original.hint
        details = original.details
        if original.ephemeral is not None:
            ephemeral = original.ephemeral
        is_expected = True
    elif isinstance(original, app_commands.CommandOnCooldown):
        title = "Slow down"
        message = "That command is on cooldown."
        hint = f"Try again in {_format_duration(original.retry_after)}."
        is_expected = True
    elif isinstance(original, app_commands.MissingPermissions):
        title = "Missing permissions"
        message = "You do not have permission to use that command."
        if getattr(original, "missing_permissions", None):
            details = [", ".join(original.missing_permissions)]
        is_expected = True
    elif isinstance(original, app_commands.BotMissingPermissions):
        title = "I need permissions"
        message = "I am missing permissions to run that command."
        if getattr(original, "missing_permissions", None):
            details = [", ".join(original.missing_permissions)]
        is_expected = True
    elif isinstance(original, app_commands.NoPrivateMessage):
        title = "Server only"
        message = "That command cannot be used in DMs."
        is_expected = True
    elif isinstance(original, app_commands.TransformerError):
        param = getattr(original, "parameter", None) or getattr(original, "param", None)
        param_name = param.name if param else "parameter"
        title = "Invalid input"
        message = f"Invalid value for `{param_name}`."
        details = [str(original)]
        is_expected = True
    elif isinstance(original, app_commands.CheckFailure):
        title = "Not allowed"
        message = "You cannot use that command here."
        is_expected = True
    elif isinstance(original, ValueError):
        title = "Invalid input"
        message = str(original) or "That input could not be processed."
        is_expected = True

    return title, message, hint, details, ephemeral, is_expected


async def _send_error_response(
    interaction: Optional[discord.Interaction],
    *,
    embed: discord.Embed,
    ephemeral: bool = True,
) -> None:
    if interaction is None:
        return
    try:
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=ephemeral)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
    except discord.HTTPException:
        logging.getLogger(__name__).exception("Failed to send error response")


async def handle_app_command_error(
    interaction: Optional[discord.Interaction],
    error: app_commands.AppCommandError,
) -> None:
    error_id = str(uuid.uuid4())[:8]
    logger = logging.getLogger(__name__)

    original = getattr(error, "original", error)
    title, message, hint, details, ephemeral, is_expected = _describe_error(original)

    log_context = {
        "error_id": error_id,
        "user": getattr(getattr(interaction, "user", None), "id", None),
        "guild": getattr(getattr(interaction, "guild", None), "id", None),
        "channel": getattr(getattr(interaction, "channel", None), "id", None),
        "command": getattr(getattr(interaction, "command", None), "qualified_name", None),
    }

    cause = original.cause if isinstance(original, UserVisibleError) else None

    if is_expected:
        logger.warning(
            "Command error %(error_id)s | user=%(user)s guild=%(guild)s channel=%(channel)s command=%(command)s",
            log_context,
            exc_info=cause,
        )
    else:
        logger.exception(
            "Command error %(error_id)s | user=%(user)s guild=%(guild)s channel=%(channel)s command=%(command)s",
            log_context,
            exc_info=original,
        )

    embed = _build_error_embed(
        title=title,
        message=message,
        hint=hint,
        details=details,
        error_id=error_id,
    )

    await _send_error_response(interaction, embed=embed, ephemeral=ephemeral)


async def handle_interaction_error(
    interaction: Optional[discord.Interaction],
    error: Exception,
    *,
    ephemeral: bool = True,
) -> None:
    error_id = str(uuid.uuid4())[:8]
    logger = logging.getLogger(__name__)

    title, message, hint, details, resolved_ephemeral, is_expected = _describe_error(
        error,
        default_ephemeral=ephemeral,
    )
    cause = error.cause if isinstance(error, UserVisibleError) else None

    log_context = {
        "error_id": error_id,
        "user": getattr(getattr(interaction, "user", None), "id", None),
        "guild": getattr(getattr(interaction, "guild", None), "id", None),
        "channel": getattr(getattr(interaction, "channel", None), "id", None),
    }

    if is_expected:
        logger.warning(
            "Interaction error %(error_id)s | user=%(user)s guild=%(guild)s channel=%(channel)s",
            log_context,
            exc_info=cause,
        )
    else:
        logger.exception(
            "Interaction error %(error_id)s | user=%(user)s guild=%(guild)s channel=%(channel)s",
            log_context,
            exc_info=error,
        )

    embed = _build_error_embed(
        title=title,
        message=message,
        hint=hint,
        details=details,
        error_id=error_id,
    )

    await _send_error_response(
        interaction,
        embed=embed,
        ephemeral=resolved_ephemeral,
    )
