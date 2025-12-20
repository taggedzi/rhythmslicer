"""Command-line interface for RhythmSlicer Pro."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Iterable, Optional

from rhythm_slicer.player_vlc import VlcPlayer


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

    subparsers.add_parser("stop", help="Stop playback")
    subparsers.add_parser("pause", help="Pause playback")
    subparsers.add_parser("resume", help="Resume playback")

    volume_parser = subparsers.add_parser("volume", help="Set volume")
    volume_parser.add_argument("level", type=_volume_type, help="0-100")

    subparsers.add_parser("status", help="Show current status")

    return parser


def _execute_command(player: VlcPlayer, args: argparse.Namespace) -> CommandResult:
    if args.command == "play":
        player.load(args.path)
        player.play()
        return CommandResult(0, f"Playing: {args.path}")
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
    return CommandResult(2, f"Unknown command: {args.command}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        player = VlcPlayer()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    result = _execute_command(player, args)
    if result.message:
        stream = sys.stdout if result.exit_code == 0 else sys.stderr
        print(result.message, file=stream)
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
