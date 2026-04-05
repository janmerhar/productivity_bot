from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Iterator

ROOT = Path(__file__).resolve().parent
WATCH_TARGETS = [
    ROOT / ".env",
    ROOT / "main.py",
    # ROOT / "abstract",
    ROOT / "classes",
    # ROOT / "cli_args",
    ROOT / "cogs",
    ROOT / "config",
    ROOT / "embeds",
    ROOT / "services",
    ROOT / "views",
]
POLL_INTERVAL_SECONDS = 0.35


def _iter_watched_files() -> Iterator[Path]:
    for target in WATCH_TARGETS:
        if not target.exists():
            continue

        if target.is_file():
            yield target
            continue

        for path in target.rglob("*.py"):
            if "__pycache__" not in path.parts:
                yield path


def _snapshot() -> dict[Path, int]:
    snapshot: dict[Path, int] = {}

    for path in _iter_watched_files():
        try:
            snapshot[path] = path.stat().st_mtime_ns
        except FileNotFoundError:
            continue

    env_file = ROOT / ".env"
    if env_file.exists():
        snapshot[env_file] = env_file.stat().st_mtime_ns

    return snapshot


def _format_changes(previous: dict[Path, int], current: dict[Path, int]) -> str:
    changed_paths = sorted(
        {
            *[path for path, mtime in current.items() if previous.get(path) != mtime],
            *[path for path in previous if path not in current],
        }
    )

    if not changed_paths:
        return "unknown change"

    relative = [path.relative_to(ROOT).as_posix() for path in changed_paths[:5]]
    if len(changed_paths) > 5:
        relative.append("...")

    return ", ".join(relative)


def _start_bot() -> subprocess.Popen[bytes]:
    command = [sys.executable, str(ROOT / "main.py")]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    kwargs: dict[str, object] = {
        "cwd": str(ROOT),
        "env": env,
    }

    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP

    return subprocess.Popen(command, **kwargs)


def _stop_bot(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=5)
        return
    except Exception:
        pass

    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _poll_for_changes(on_change: Callable[[str], None]) -> None:
    previous = _snapshot()

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        current = _snapshot()
        if current == previous:
            continue

        description = _format_changes(previous, current)
        previous = current
        on_change(description)


def _watch_with_watchfiles(on_change: Callable[[str], None]) -> None:
    from watchfiles import watch

    def _watch_filter(_change: object, path: str) -> bool:
        candidate = Path(path)
        return candidate.name == ".env" or candidate.suffix == ".py"

    watched_paths = [str(path) for path in WATCH_TARGETS if path.exists()]
    for changes in watch(
        *watched_paths,
        watch_filter=_watch_filter,
        debounce=300,
        step=50,
        raise_interrupt=False,
    ):
        if not changes:
            continue

        paths = sorted(Path(path) for _, path in changes)
        description = ", ".join(
            path.relative_to(ROOT).as_posix()
            for path in paths[:5]
            if path.is_relative_to(ROOT)
        )
        if len(paths) > 5:
            description = f"{description}, ..."
        on_change(description or "unknown change")


def main() -> None:
    try:
        import watchfiles  # noqa: F401
    except ImportError:
        watcher = _poll_for_changes
        backend = "polling"
    else:
        watcher = _watch_with_watchfiles
        backend = "watchfiles"

    print(f"[dev] Starting bot with {backend} autoreload.")
    process = _start_bot()

    def _restart(description: str) -> None:
        nonlocal process
        print(f"[dev] Change detected in {description}. Restarting bot...")
        _stop_bot(process)
        process = _start_bot()

    try:
        watcher(_restart)
    finally:
        _stop_bot(process)


if __name__ == "__main__":
    main()
