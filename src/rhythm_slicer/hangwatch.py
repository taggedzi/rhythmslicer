"""Hang watchdog and faulthandler integration."""

from __future__ import annotations

import faulthandler
import threading
import time
from pathlib import Path
from typing import Callable, Optional, TextIO

_HANG_FILE: Optional[TextIO] = None
_HANG_PATH: Optional[Path] = None
_LOCK = threading.Lock()


def enable_faulthandler(log_path: Path) -> Path:
    """Enable faulthandler and return the hangdump path."""
    hang_path = log_path.parent / "hangdump.log"
    try:
        hang_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(hang_path, "a", encoding="utf-8")
    except Exception:
        return hang_path
    with _LOCK:
        global _HANG_FILE, _HANG_PATH
        _HANG_FILE = handle
        _HANG_PATH = hang_path
    try:
        faulthandler.enable(file=handle, all_threads=True)
    except Exception:
        pass
    return hang_path


def _write_header(label: str) -> None:
    handle = _HANG_FILE
    if not handle:
        return
    stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    try:
        handle.write(f"\n[{stamp}] {label}\n")
        handle.flush()
    except Exception:
        pass


def dump_threads(label: str) -> None:
    """Write a stack dump header and dump all threads."""
    _write_header(label)
    handle = _HANG_FILE
    if not handle:
        return
    try:
        faulthandler.dump_traceback(file=handle, all_threads=True)
        handle.flush()
    except Exception:
        pass


class HangWatchdog:
    """Background hang watchdog that dumps threads when UI stops ticking."""

    def __init__(
        self,
        get_last_tick: Callable[[], float],
        *,
        threshold_seconds: float = 15.0,
        repeat_seconds: float = 30.0,
        poll_seconds: float = 1.0,
    ) -> None:
        self._get_last_tick = get_last_tick
        self._threshold_seconds = threshold_seconds
        self._repeat_seconds = repeat_seconds
        self._poll_seconds = poll_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="HangWatchdog", daemon=True
        )
        self._last_dump = 0.0

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            try:
                last_tick = self._get_last_tick()
            except Exception:
                last_tick = now
            stalled = now - last_tick > self._threshold_seconds
            if stalled and now - self._last_dump > self._repeat_seconds:
                self._last_dump = now
                dump_threads("hang detected")
            self._stop_event.wait(self._poll_seconds)
