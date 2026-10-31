"""Restart a local development process when watched source files change."""

from __future__ import annotations

import argparse
import os
import shlex
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".local",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "target",
    }
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--watch", action="append", required=True, help="path to watch; repeatable")
    parser.add_argument(
        "--suffix",
        action="append",
        default=[],
        help="file suffix or exact filename to watch; repeatable",
    )
    parser.add_argument(
        "--cwd", default=".", help="command working directory, relative to repo root"
    )
    parser.add_argument(
        "--command-env", help="environment variable containing a shell-quoted command"
    )
    parser.add_argument("--poll-interval", type=float, default=0.4)
    parser.add_argument("--debounce", type=float, default=0.35)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command and args.command[0] == "--":
        args.command = args.command[1:]
    if not 0.05 <= args.poll_interval <= 10:
        parser.error("--poll-interval must be between 0.05 and 10 seconds")
    if not 0 <= args.debounce <= 10:
        parser.error("--debounce must be between 0 and 10 seconds")
    if args.command_env and args.command:
        parser.error("provide either --command-env or a command after --, not both")
    if args.command_env:
        args.command = shlex.split(os.environ.get(args.command_env, ""))
    if not args.command:
        parser.error("a command is required after -- or through --command-env")
    return args


def resolve_paths(root: Path, paths: Sequence[str]) -> list[Path]:
    return [
        (root / path).resolve() if not Path(path).is_absolute() else Path(path) for path in paths
    ]


def file_state(path: Path) -> tuple[int, int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    if not path.is_file():
        return None
    return stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size


def is_watched(path: Path, suffixes: frozenset[str]) -> bool:
    return not suffixes or path.suffix in suffixes or path.name in suffixes


def snapshot(paths: Sequence[Path], suffixes: frozenset[str]) -> dict[Path, tuple[int, int, int]]:
    state: dict[Path, tuple[int, int, int]] = {}
    for watched_path in paths:
        if watched_path.is_file():
            current = file_state(watched_path)
            if current is not None and is_watched(watched_path, suffixes):
                state[watched_path] = current
            continue
        if not watched_path.is_dir():
            continue
        for directory, directory_names, file_names in os.walk(watched_path):
            directory_names[:] = sorted(
                name
                for name in directory_names
                if name not in IGNORED_DIRECTORIES and not (Path(directory) / name).is_symlink()
            )
            for file_name in file_names:
                file_path = Path(directory) / file_name
                if not is_watched(file_path, suffixes):
                    continue
                current = file_state(file_path)
                if current is not None:
                    state[file_path] = current
    return state


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
        process.wait(timeout=5)
    except ProcessLookupError:
        return
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.wait()


def start_process(command: Sequence[str], cwd: Path) -> subprocess.Popen[bytes]:
    print(f"[dev-watch] starting {command[0]}", flush=True)
    return subprocess.Popen(
        command,
        cwd=cwd,
        start_new_session=(os.name == "posix"),
    )


def run(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[1]
    watch_paths = resolve_paths(root, args.watch)
    cwd = resolve_paths(root, [args.cwd])[0]
    suffixes = frozenset(args.suffix)
    changed_files = snapshot(watch_paths, suffixes)
    shutdown = False

    def request_shutdown(_signum: int, _frame: object) -> None:
        nonlocal shutdown
        shutdown = True

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)

    process = start_process(args.command, cwd)
    try:
        while not shutdown:
            time.sleep(args.poll_interval)
            current = snapshot(watch_paths, suffixes)
            if current == changed_files:
                continue
            changed_files = current
            stable_since = time.monotonic()
            while not shutdown:
                time.sleep(args.poll_interval)
                latest = snapshot(watch_paths, suffixes)
                if latest != changed_files:
                    changed_files = latest
                    stable_since = time.monotonic()
                if time.monotonic() - stable_since >= args.debounce:
                    break
            if shutdown:
                break
            print("[dev-watch] source changed; restarting", flush=True)
            stop_process(process)
            process = start_process(args.command, cwd)
    finally:
        stop_process(process)
    return 0


def main() -> int:
    return run(parse_args())


if __name__ == "__main__":
    sys.exit(main())
