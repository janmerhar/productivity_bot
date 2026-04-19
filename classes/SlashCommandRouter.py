import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, get_args, get_origin

import discord
from discord import app_commands

from classes.OpenAIFunctions import OpenAIFunctions, DEFAULT_OPENAI_MODEL
from config.env import settings
from services.error_reporting import UserVisibleError, ValidationError
from services.visibility import visibility_value_from_ephemeral


class SlashCommandRouter:
    def __init__(
        self,
        tree: app_commands.CommandTree,
        excluded: Optional[set[str]] = None,
        context_path: Optional[str] = None,
    ):
        self.tree = tree
        self.excluded = excluded or set()
        self.context_path = context_path or "config/run_context.txt"
        self.context_text = self._load_context()

    def _load_context(self) -> str:
        path = Path(self.context_path)
        if not path.exists() or not path.is_file():
            return ""
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            return ""
        cleaned = text.strip()
        if not cleaned:
            return ""
        return cleaned[:4000]

    def _iter_leaf_commands(self) -> List[app_commands.Command]:
        commands: List[app_commands.Command] = []
        for command in self.tree.walk_commands():
            if isinstance(command, app_commands.Group):
                continue
            if command.qualified_name in self.excluded or command.name in self.excluded:
                continue
            commands.append(command)
        return commands

    @staticmethod
    def _param_schema(param: app_commands.Parameter) -> Dict[str, Any]:
        schema: Dict[str, Any] = {
            "name": param.name,
            "description": param.description or "",
            "required": param.required,
        }
        option_type = getattr(param, "type", None)
        if option_type is not None:
            schema["type"] = getattr(option_type, "name", str(option_type))
        choices = getattr(param, "choices", None)
        if choices:
            schema["choices"] = [
                {"name": choice.name, "value": choice.value} for choice in choices
            ]
        return schema

    def _command_catalog(
        self,
    ) -> Tuple[Dict[str, app_commands.Command], List[Dict[str, Any]]]:
        catalog: List[Dict[str, Any]] = []
        command_map: Dict[str, app_commands.Command] = {}
        for command in self._iter_leaf_commands():
            command_map[command.qualified_name] = command
            catalog.append(
                {
                    "name": command.qualified_name,
                    "description": command.description or "",
                    "parameters": [
                        self._param_schema(param) for param in command.parameters
                    ],
                }
            )
        return command_map, catalog

    def _parse_query(
        self, query: str, catalog: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        api_key = settings.openai_api_key
        if not api_key:
            return None

        system_prompt = (
            "You map user requests to existing Discord slash commands. "
            "Pick the single best command from the list. "
            "Return JSON with keys: command (string or null) and arguments (object). "
            "Use exact command names and parameter names from the list. "
            "Include only arguments that are explicitly provided or strongly implied. "
            "If nothing matches, set command to null and arguments to {}."
        )
        user_prompt = (
            f"Request: {query}\n" f"Commands: {json.dumps(catalog, ensure_ascii=True)}"
        )
        if self.context_text:
            user_prompt = f"Context: {self.context_text}\n" + user_prompt

        payload = OpenAIFunctions._chat_json_safe(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=DEFAULT_OPENAI_MODEL,
            api_key=api_key,
        )
        if not payload:
            return None

        command = payload.get("command")
        args = payload.get("arguments", {})
        if command is not None:
            command = str(command).strip()
        if not isinstance(args, dict):
            args = {}

        return {"command": command, "arguments": args}

    @staticmethod
    def _unwrap_optional(annotation: Any) -> Any:
        origin = get_origin(annotation)
        if origin is Union:
            args = [arg for arg in get_args(annotation) if arg is not type(None)]
            if len(args) == 1:
                return args[0]
        return annotation

    @staticmethod
    def _is_choice_annotation(annotation: Any) -> bool:
        if annotation is app_commands.Choice:
            return True
        origin = get_origin(annotation)
        return origin is app_commands.Choice

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"true", "yes", "y", "1"}:
            return True
        if text in {"false", "no", "n", "0"}:
            return False
        raise ValueError("expected true/false")

    @staticmethod
    def _coerce_number(value: Any, integer: bool) -> Any:
        if isinstance(value, (int, float)) and not integer:
            return float(value)
        if isinstance(value, int) and integer:
            return value
        text = str(value).strip()
        return int(text) if integer else float(text)

    @staticmethod
    def _resolve_channel(
        interaction: discord.Interaction,
        value: Any,
        channel_type: Optional[type] = None,
    ) -> Optional[discord.abc.GuildChannel]:
        if interaction.guild is None:
            return None
        channel_id = None
        if isinstance(value, int):
            channel_id = value
        else:
            text = str(value).strip()
            if text.isdigit():
                channel_id = int(text)
        if channel_id is not None:
            channel = interaction.guild.get_channel(channel_id)
            if channel and (channel_type is None or isinstance(channel, channel_type)):
                return channel

        name = str(value).strip().lstrip("#")
        for channel in interaction.guild.channels:
            if channel.name == name:
                if channel_type is None or isinstance(channel, channel_type):
                    return channel
        return None

    def _coerce_choice(
        self, param: app_commands.Parameter, value: Any
    ) -> app_commands.Choice:
        choices = getattr(param, "choices", None) or []
        for choice in choices:
            if str(choice.value).lower() == str(value).lower():
                return choice
            if str(choice.name).lower() == str(value).lower():
                return choice
        if choices:
            names = ", ".join(choice.name for choice in choices)
            raise ValueError(f"expected one of: {names}")
        return app_commands.Choice(name=str(value), value=value)

    def _coerce_argument(
        self,
        param: app_commands.Parameter,
        value: Any,
        interaction: discord.Interaction,
    ) -> Any:
        annotation = self._unwrap_optional(getattr(param, "annotation", None))
        if self._is_choice_annotation(annotation):
            return self._coerce_choice(param, value)

        if annotation in {int, float, bool, str}:
            if annotation is int:
                return self._coerce_number(value, integer=True)
            if annotation is float:
                return self._coerce_number(value, integer=False)
            if annotation is bool:
                return self._coerce_bool(value)
            return str(value)

        if isinstance(annotation, type) and issubclass(
            annotation, discord.abc.GuildChannel
        ):
            resolved = self._resolve_channel(
                interaction,
                value,
                channel_type=annotation,
            )
            if resolved is None:
                raise ValueError("channel not found")
            return resolved

        if isinstance(annotation, type) and issubclass(
            annotation, discord.VoiceChannel
        ):
            resolved = self._resolve_channel(
                interaction,
                value,
                channel_type=discord.VoiceChannel,
            )
            if resolved is None:
                raise ValueError("voice channel not found")
            return resolved

        return value

    def _coerce_arguments(
        self,
        command: app_commands.Command,
        arguments: Dict[str, Any],
        interaction: discord.Interaction,
    ) -> Tuple[Dict[str, Any], List[str], List[str]]:
        coerced: Dict[str, Any] = {}
        missing: List[str] = []
        invalid: List[str] = []
        for param in command.parameters:
            if param.name not in arguments:
                if param.required:
                    missing.append(param.name)
                continue
            try:
                coerced[param.name] = self._coerce_argument(
                    param, arguments[param.name], interaction
                )
            except Exception as exc:
                invalid.append(f"{param.name}: {exc}")
        return coerced, missing, invalid

    async def dispatch(
        self,
        interaction: discord.Interaction,
        query: str,
        ephemeral_default: bool = False,
    ) -> None:
        query_text = query.strip()
        if not query_text:
            raise ValidationError(
                "Please provide instructions to run a command.",
                hint="Try: /assistant run query: create a todo called Buy milk",
                ephemeral=ephemeral_default,
            )

        command_map, catalog = self._command_catalog()
        if not command_map:
            raise UserVisibleError(
                "No slash commands are available to run.",
                ephemeral=ephemeral_default,
            )

        payload = await asyncio.to_thread(self._parse_query, query_text, catalog)
        if payload is None:
            raise UserVisibleError(
                "I could not parse that request.",
                hint="Make sure OpenAI is configured.",
                ephemeral=ephemeral_default,
            )

        command_name = payload.get("command") or ""
        args = payload.get("arguments", {})
        if not command_name:
            raise UserVisibleError(
                "I could not find a matching command for that request.",
                hint="Try being more specific or naming the command you want.",
                ephemeral=ephemeral_default,
            )

        command = command_map.get(command_name)
        if command is None:
            raise UserVisibleError(
                f"Command `{command_name}` is not available.",
                ephemeral=ephemeral_default,
            )

        coerced, missing, invalid = self._coerce_arguments(command, args, interaction)
        if "visibility" not in coerced:
            for param in command.parameters:
                if param.name == "visibility":
                    default_value = visibility_value_from_ephemeral(ephemeral_default)
                    coerced["visibility"] = self._coerce_choice(param, default_value)
                    break
        if missing or invalid:
            parts: List[str] = []
            if missing:
                parts.append(f"Missing: {', '.join(missing)}")
            if invalid:
                parts.append(f"Invalid: {', '.join(invalid)}")
            raise ValidationError(
                f"Matched `{command_name}`, but the arguments were invalid.",
                details=parts,
                hint="Check the parameter names and values for that command.",
                ephemeral=ephemeral_default,
            )

        proxy = RoutedInteraction(interaction, ephemeral_default)
        bound = command.binding
        if bound is None:
            await command.callback(proxy, **coerced)
        else:
            await command.callback(bound, proxy, **coerced)


class RoutedInteractionResponse:
    def __init__(
        self, interaction: discord.Interaction, ephemeral_default: bool
    ) -> None:
        self._interaction = interaction
        self._ephemeral_default = ephemeral_default

    def is_done(self) -> bool:
        return self._interaction.response.is_done()

    async def defer(self, *, thinking: bool = False, ephemeral: Optional[bool] = None):
        if self._interaction.response.is_done():
            return None
        if ephemeral is None:
            ephemeral = self._ephemeral_default
        return await self._interaction.response.defer(
            thinking=thinking,
            ephemeral=ephemeral,
        )

    async def send_message(self, *args: Any, **kwargs: Any):
        if "ephemeral" not in kwargs:
            kwargs["ephemeral"] = self._ephemeral_default
        if self._interaction.response.is_done():
            return await self._interaction.followup.send(*args, **kwargs)
        return await self._interaction.response.send_message(*args, **kwargs)


class RoutedInteractionFollowup:
    def __init__(self, followup: Any, ephemeral_default: bool):
        self._followup = followup
        self._ephemeral_default = ephemeral_default

    async def send(self, *args: Any, **kwargs: Any):
        if "ephemeral" not in kwargs:
            kwargs["ephemeral"] = self._ephemeral_default
        return await self._followup.send(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._followup, name)


class RoutedInteraction:
    def __init__(
        self, interaction: discord.Interaction, ephemeral_default: bool
    ) -> None:
        self._interaction = interaction
        self.response = RoutedInteractionResponse(interaction, ephemeral_default)
        self.followup = RoutedInteractionFollowup(
            interaction.followup, ephemeral_default
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._interaction, name)
