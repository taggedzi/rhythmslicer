"""Frame player for the visualizer."""

from __future__ import annotations

import asyncio
import logging
from typing import Iterator, Optional, TYPE_CHECKING

from textual.timer import Timer

from rhythm_slicer.hackscript import HackFrame

if TYPE_CHECKING:
    from rhythm_slicer.tui import RhythmSlicerApp

logger = logging.getLogger(__name__)


class FramePlayer:
    """Non-blocking HackScript frame player for the visualizer."""

    def __init__(self, app: "RhythmSlicerApp") -> None:
        self._app = app
        self._frames: Optional[Iterator[HackFrame]] = None
        self._timer: Optional[Timer] = None

    def start(
        self,
        frames: Iterator[HackFrame],
        *,
        first_frame: HackFrame | None = None,
    ) -> None:
        self.stop()
        self._frames = frames
        if first_frame is not None:
            self._app._show_frame(first_frame)
            self._schedule_next(first_frame.hold_ms)
        else:
            self._advance()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._frames = None

    @property
    def is_running(self) -> bool:
        return self._frames is not None

    def _advance(self) -> None:
        if self._frames is None:
            return
        try:
            frame = next(self._frames)
        except Exception as exc:
            logger.exception("Visualizer frame error")
            self._app._set_message(f"Visualizer error: {exc}", level="error")
            self.stop()
            return
        except StopIteration:
            self.stop()
            return
        self._app._show_frame(frame)
        self._schedule_next(frame.hold_ms)

    def _schedule_next(self, hold_ms: int) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.stop()
            return
        delay = max(0.01, hold_ms / 1000.0)
        self._timer = self._app.set_timer(delay, self._advance)
