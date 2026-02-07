from typing import Optional

from discord import app_commands

VISIBILITY_DESC = "Who can see this response"
VISIBILITY_CHOICES = [
    app_commands.Choice(name="Private (only me)", value="private"),
    app_commands.Choice(name="Public (channel)", value="public"),
]


def resolve_visibility(
    visibility: Optional[app_commands.Choice[str]],
    default: str,
) -> bool:
    value = visibility.value if visibility else default
    return value == "private"


def visibility_value_from_ephemeral(ephemeral_default: bool) -> str:
    return "private" if ephemeral_default else "public"
