"""Command-line interface for RhythmSlicer Pro."""

from __future__ import annotations

import argparse
import sys
import logging
import threading
from typing import Iterable, Optional, Tuple
from types import TracebackType

from rhythm_slicer.player_vlc import VlcPlayer
from rhythm_slicer.logging_setup import init_logging
from rhythm_slicer.hangwatch import enable_faulthandler, dump_threads

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(prog="r-slicer", description="RhythmSlicer Pro")
    parser.add_argument(
        "path",
        nargs="?",
        default="",
        help="Path to media file or playlist",
    )
    parser.add_argument(
        "--viz",
        default=None,
        help="Visualization name for the TUI",
    )

    return parser


def _run_tui(path: str, player: VlcPlayer, viz_name: Optional[str]) -> int:
    try:
        from rhythm_slicer.tui import run_tui
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return run_tui(path, player, viz_name=viz_name)


def main(argv: Optional[Iterable[str]] = None) -> int:
    """Entry point for the CLI."""
    log_path = init_logging()
    enable_faulthandler(log_path)
    logger.info("App start")

    def excepthook(exc_type, exc, tb) -> None:
        logger.exception("Uncaught exception", exc_info=(exc_type, exc, tb))
        dump_threads("uncaught exception")

    sys.excepthook = excepthook

    if hasattr(threading, "excepthook"):

        def thread_hook(args: threading.ExceptHookArgs) -> None:
            exc_value = args.exc_value or RuntimeError("unknown")
            exc_info: Tuple[
                type[BaseException], BaseException, Optional[TracebackType]
            ] = (
                args.exc_type,
                exc_value,
                args.exc_traceback,
            )
            thread_name = args.thread.name if args.thread else "thread"
            logger.exception("Thread exception in %s", thread_name, exc_info=exc_info)

        threading.excepthook = thread_hook

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        player = VlcPlayer()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    exit_code = _run_tui(args.path, player, args.viz)
    logger.info("App exit code=%s", exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
