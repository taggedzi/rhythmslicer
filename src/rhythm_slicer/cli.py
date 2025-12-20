"""Command-line interface for RhythmSlicer Pro."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional
from pathlib import Path

from rhythm_slicer.player_vlc import VlcPlayer
from rhythm_slicer.playlist import load_from_input
from rhythm_slicer.playlist_io import save_m3u8


@dataclass(frozen=True)
class CommandResult:
    """Result of executing a CLI command."""

    exit_code: int
    message: Optional[str] = None


def _volume_type(value: str) -> int:
    try:
        volume = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("volume must be an integer") from exc
    if not 0 <= volume <= 100:
        raise argparse.ArgumentTypeError("volume must be between 0 and 100")
    return volume


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="r-slicer", description="RhythmSlicer Pro")
    subparsers = parser.add_subparsers(dest="command", required=True)

    play_parser = subparsers.add_parser("play", help="Play a media file")
    play_parser.add_argument("path", help="Path to media file")
    play_parser.add_argument(
        "--wait",
        dest="wait",
        action="store_true",
        default=True,
        help="Wait for playback to finish (default)",
    )
    play_parser.add_argument(
        "--no-wait",
        dest="wait",
        action="store_false",
        help="Exit immediately after starting playback",
    )
    play_parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch the Textual TUI instead of the basic CLI playback",
    )

    tui_parser = subparsers.add_parser("tui", help="Launch the TUI player")
    tui_parser.add_argument("path", help="Path to media file")

    subparsers.add_parser("stop", help="Stop playback")
    subparsers.add_parser("pause", help="Pause playback")
    subparsers.add_parser("resume", help="Resume playback")

    volume_parser = subparsers.add_parser("volume", help="Set volume")
    volume_parser.add_argument("level", type=_volume_type, help="0-100")

    subparsers.add_parser("status", help="Show current status")

    playlist_parser = subparsers.add_parser("playlist", help="Playlist utilities")
    playlist_sub = playlist_parser.add_subparsers(dest="playlist_cmd", required=True)

    save_parser = playlist_sub.add_parser("save", help="Save playlist to M3U8")
    save_parser.add_argument("dest", help="Destination .m3u8 path")
    save_parser.add_argument("--from", dest="from_input", required=True)
    save_parser.add_argument(
        "--absolute",
        action="store_true",
        help="Save with absolute paths",
    )

    show_parser = playlist_sub.add_parser("show", help="Show resolved tracks")
    show_parser.add_argument("--from", dest="from_input", required=True)

    return parser


def _is_terminal_state(state: str) -> bool:
    return state in {"ended", "stopped", "stop"}


def _format_status(player: VlcPlayer, state: str) -> str:
    position = player.get_position_ms()
    length = player.get_length_ms()
    if position is not None and length is not None and length > 0:
        return f"{state} {position}ms / {length}ms"
    return f"{state}"


def _wait_for_playback(
    player: VlcPlayer,
    *,
    printer: Callable[[str], None],
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> None:
    last_print = 0.0
    try:
        while True:
            state = player.get_state()
            if _is_terminal_state(state):
                return
            current_time = now()
            if current_time - last_print >= 1.0:
                printer(_format_status(player, state))
                last_print = current_time
            sleep(0.1)
    except KeyboardInterrupt:
        player.stop()


def _execute_command(player: VlcPlayer, args: argparse.Namespace) -> CommandResult:
    if args.command == "play":
        player.load(args.path)
        player.play()
        return CommandResult(0, f"Playing: {args.path}")
    if args.command == "tui":
        return CommandResult(0)
    if args.command == "stop":
        player.stop()
        return CommandResult(0, "Stopped")
    if args.command == "pause":
        player.pause()
        return CommandResult(0, "Paused")
    if args.command == "resume":
        player.play()
        return CommandResult(0, "Resumed")
    if args.command == "volume":
        player.set_volume(args.level)
        return CommandResult(0, f"Volume set to {args.level}")
    if args.command == "status":
        state = player.get_state()
        media = player.current_media or "none"
        return CommandResult(0, f"State: {state}, Media: {media}")
    if args.command == "playlist":
        playlist = load_from_input(Path(args.from_input))
        if args.playlist_cmd == "save":
            if playlist.is_empty():
                return CommandResult(1, "No tracks to save")
            mode = "absolute" if args.absolute else "auto"
            save_m3u8(playlist, Path(args.dest), mode=mode)
            return CommandResult(0, f"Saved {len(playlist.tracks)} tracks to {args.dest}")
        if args.playlist_cmd == "show":
            lines = [
                f"{idx + 1}\t{track.path}"
                for idx, track in enumerate(playlist.tracks)
            ]
            return CommandResult(0, "\n".join(lines))
        return CommandResult(2, f"Unknown playlist command: {args.playlist_cmd}")
    return CommandResult(2, f"Unknown command: {args.command}")


def _run_tui(path: str, player: VlcPlayer) -> int:
    try:
        from rhythm_slicer.tui import run_tui
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return run_tui(path, player)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        player = VlcPlayer()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.command == "tui":
        return _run_tui(args.path, player)
    if args.command == "play" and getattr(args, "tui", False):
        return _run_tui(args.path, player)

    result = _execute_command(player, args)
    if result.message:
        stream = sys.stdout if result.exit_code == 0 else sys.stderr
        print(result.message, file=stream)
    if args.command == "play" and getattr(args, "wait", False) and result.exit_code == 0:
        _wait_for_playback(player, printer=print)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
