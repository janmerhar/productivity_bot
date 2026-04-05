from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import discord
from discord.ext import tasks

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _disable_background_loops() -> None:
    def _noop_start(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return None

    tasks.Loop.start = _noop_start  # type: ignore[assignment]


_disable_background_loops()

import main  # noqa: E402
from config.env import env  # noqa: E402


@dataclass(frozen=True)
class ScopeReport:
    label: str
    desired_root_count: int
    remote_root_count: int
    desired: tuple[str, ...]
    remote: tuple[str, ...]

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.desired) - set(self.remote)))

    @property
    def stale(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.remote) - set(self.desired)))

    @property
    def clean(self) -> bool:
        return not self.missing and not self.stale


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit or clean Discord application commands without changing the "
            "bot's normal startup sync behavior."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Apply cleanup. Without this flag the script only reports diffs."
        ),
    )
    parser.add_argument(
        "--skip-global",
        action="store_true",
        help="Do not sync global commands during apply.",
    )
    parser.add_argument(
        "--skip-dev",
        action="store_true",
        help="Do not sync the configured DEV_GUILD_ID during apply.",
    )
    parser.add_argument(
        "--skip-legacy-guilds",
        action="store_true",
        help=(
            "Do not clear guild-scoped commands from non-dev guilds during apply."
        ),
    )
    return parser.parse_args()


def _is_dev_mode() -> bool:
    return str(env.get("DEV_MODE", "")).strip().lower() == "true"


def _dev_guild_id() -> int | None:
    raw = env.get("DEV_GUILD_ID")
    if not raw:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _enabled_extension_modules() -> set[str]:
    return set(main.bot.extensions.keys())


def _command_module(
    command: discord.app_commands.Command
    | discord.app_commands.Group
    | discord.app_commands.ContextMenu,
) -> str | None:
    module = getattr(command, "module", None)
    if isinstance(module, str) and module:
        return module

    callback = getattr(command, "callback", None)
    callback_module = getattr(callback, "__module__", None)
    if isinstance(callback_module, str) and callback_module:
        return callback_module

    binding = getattr(command, "binding", None)
    binding_module = getattr(binding, "__module__", None)
    if isinstance(binding_module, str) and binding_module:
        return binding_module

    return None


def _prune_unloaded_extension_commands() -> list[str]:
    enabled_modules = _enabled_extension_modules()
    removed: list[str] = []

    for command in list(main.bot.tree.get_commands(type=None)):
        module = _command_module(command)
        if module in enabled_modules:
            continue

        command_type = getattr(
            command,
            "type",
            discord.AppCommandType.chat_input,
        )
        main.bot.tree.remove_command(command.name, type=command_type)
        removed.append(f"{command_type.name}:{command.name} ({module or 'unknown'})")

    return removed


def _walk_local_commands(
    commands: Iterable[discord.app_commands.Command | discord.app_commands.Group | discord.app_commands.ContextMenu],
    prefix: Sequence[str] = (),
) -> Iterable[str]:
    for command in commands:
        if isinstance(command, discord.app_commands.ContextMenu):
            yield f"{command.type.name}:{command.name}"
            continue

        child_prefix = [*prefix, command.name]
        children = list(getattr(command, "commands", ()))
        if not children:
            yield f"chat_input:{' '.join(child_prefix)}"
            continue

        yield from _walk_local_commands(children, child_prefix)


def _walk_remote_command(
    command: discord.app_commands.AppCommand,
    prefix: Sequence[str] = (),
) -> Iterable[str]:
    if command.type is not discord.AppCommandType.chat_input:
        yield f"{command.type.name}:{command.name}"
        return

    options = list(command.options or [])
    subcommands = [
        option
        for option in options
        if option.type
        in (
            discord.AppCommandOptionType.subcommand,
            discord.AppCommandOptionType.subcommand_group,
        )
    ]
    if not subcommands:
        yield f"chat_input:{' '.join([*prefix, command.name])}"
        return

    root = [*prefix, command.name]
    for option in subcommands:
        yield from _walk_remote_option(option, root)


def _walk_remote_option(
    option: discord.app_commands.Argument,
    prefix: Sequence[str],
) -> Iterable[str]:
    path = [*prefix, option.name]
    if option.type is discord.AppCommandOptionType.subcommand:
        yield f"chat_input:{' '.join(path)}"
        return

    for child in option.options or []:
        yield from _walk_remote_option(child, path)


def _desired_global_paths() -> tuple[str, ...]:
    commands = main.bot.tree.get_commands()
    return tuple(sorted(set(_walk_local_commands(commands))))


async def _remote_paths(
    guild: discord.abc.Snowflake | None = None,
) -> tuple[str, ...]:
    commands = await main.bot.tree.fetch_commands(guild=guild)
    paths: set[str] = set()
    for command in commands:
        paths.update(_walk_remote_command(command))
    return tuple(sorted(paths))


async def _remote_root_count(
    guild: discord.abc.Snowflake | None = None,
) -> int:
    commands = await main.bot.tree.fetch_commands(guild=guild)
    return len(commands)


def _desired_root_count() -> int:
    return len(main.bot.tree.get_commands(type=None))


def _render_report(report: ScopeReport) -> str:
    lines = [
        report.label,
        (
            "  root_commands "
            f"local={report.desired_root_count} remote={report.remote_root_count}"
        ),
        (
            "  executable_paths "
            f"local={len(report.desired)} remote={len(report.remote)}"
        ),
    ]

    if report.clean:
        lines.append("  status=clean")
        return "\n".join(lines)

    lines.append(f"  missing={len(report.missing)} stale={len(report.stale)}")
    if report.missing:
        lines.append("  missing commands:")
        lines.extend(f"    {path}" for path in report.missing)
    if report.stale:
        lines.append("  stale commands:")
        lines.extend(f"    {path}" for path in report.stale)
    return "\n".join(lines)


async def _build_reports() -> list[ScopeReport]:
    reports: list[ScopeReport] = []
    desired_global = _desired_global_paths()
    remote_global = await _remote_paths()
    desired_global_roots = _desired_root_count()
    remote_global_roots = await _remote_root_count()
    reports.append(
        ScopeReport(
            label="Global",
            desired_root_count=desired_global_roots,
            remote_root_count=remote_global_roots,
            desired=desired_global,
            remote=remote_global,
        )
    )

    dev_guild_id = _dev_guild_id()
    if _is_dev_mode() and dev_guild_id is not None:
        dev_scope = discord.Object(id=dev_guild_id)
        remote_dev = await _remote_paths(guild=dev_scope)
        reports.append(
            ScopeReport(
                label=f"Dev Guild ({dev_guild_id})",
                desired_root_count=desired_global_roots,
                remote_root_count=await _remote_root_count(guild=dev_scope),
                desired=desired_global,
                remote=remote_dev,
            )
        )

    for guild in sorted(main.bot.guilds, key=lambda item: item.id):
        if guild.id == dev_guild_id:
            continue
        remote_guild = await _remote_paths(guild=guild)
        if not remote_guild:
            continue
        reports.append(
            ScopeReport(
                label=f"Legacy Guild Scope: {guild.name} ({guild.id})",
                desired_root_count=0,
                remote_root_count=await _remote_root_count(guild=guild),
                desired=(),
                remote=remote_guild,
            )
        )

    return reports


async def _apply_cleanup(args: argparse.Namespace) -> list[str]:
    actions: list[str] = []
    dev_guild_id = _dev_guild_id()

    if not args.skip_global:
        synced = await main.bot.tree.sync()
        actions.append(
            f"Synced global commands ({len(synced)} root commands)."
        )

    if not args.skip_dev and _is_dev_mode() and dev_guild_id is not None:
        dev_scope = discord.Object(id=dev_guild_id)
        main.bot.tree.clear_commands(guild=dev_scope)
        main.bot.tree.copy_global_to(guild=dev_scope)
        synced = await main.bot.tree.sync(guild=dev_scope)
        actions.append(
            f"Synced dev guild {dev_guild_id} ({len(synced)} root commands)."
        )

    if not args.skip_legacy_guilds:
        for guild in sorted(main.bot.guilds, key=lambda item: item.id):
            if guild.id == dev_guild_id:
                continue
            current = await main.bot.tree.fetch_commands(guild=guild)
            if not current:
                continue
            main.bot.tree.clear_commands(guild=guild)
            await main.bot.tree.sync(guild=guild)
            actions.append(
                f"Cleared {len(current)} guild-scoped commands from "
                f"{guild.name} ({guild.id})."
            )

    return actions


async def _run(args: argparse.Namespace) -> int:
    main.env["SYNC_COMMANDS_ON_START"] = "false"
    await main.load()
    pruned_commands = _prune_unloaded_extension_commands()

    completed = asyncio.Event()
    exit_code = 0

    @main.bot.listen("on_ready")
    async def _once_ready() -> None:
        nonlocal exit_code
        if completed.is_set():
            return

        try:
            if pruned_commands:
                print("Ignored local commands from unloaded extensions")
                print("============================================")
                for command in pruned_commands:
                    print(command)
                print()

            reports = await _build_reports()
            print("Command scope audit")
            print("===================")
            for report in reports:
                print(_render_report(report))
                print()

            if args.apply:
                print("Applying cleanup")
                print("================")
                for line in await _apply_cleanup(args):
                    print(line)
                print()
                print("Post-cleanup audit")
                print("==================")
                for report in await _build_reports():
                    print(_render_report(report))
                    print()
        except Exception:
            exit_code = 1
            raise
        finally:
            completed.set()
            await main.bot.close()

    await main.bot.start(env["DISCORD_TOKEN"])
    return exit_code


def main_cli() -> int:
    args = _parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main_cli())
