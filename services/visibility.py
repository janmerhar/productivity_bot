from typing import Optional, Union

from discord import app_commands

VISIBILITY_DESC = "Who can see this response"
VISIBILITY_CHOICES = [
    app_commands.Choice(name="Private (only me)", value="private"),
    app_commands.Choice(name="Public (channel)", value="public"),
]


def resolve_visibility(
    visibility: Optional[Union[app_commands.Choice[str], str]],
    default: str,
) -> bool:
    value = visibility.value if isinstance(visibility, app_commands.Choice) else visibility
    if value is None:
        value = default
    return value == "private"


def visibility_value_from_ephemeral(ephemeral_default: bool) -> str:
    return "private" if ephemeral_default else "public"
