"""Marquee widget for scrolling single-line text."""

from __future__ import annotations

from typing import Optional

from textual import events
from textual.timer import Timer
from textual.widgets import Static


class Marquee(Static):
    """Single-line marquee display for long text."""

    def __init__(
        self,
        text: str = "",
        *,
        step_interval: float = 0.14,
        start_pause: float = 0.8,
        loop_pause: float = 0.6,
        separator: str = "   -   ",
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__("", name=name, id=id, classes=classes, disabled=disabled)
        self._full_text = ""
        self._buffer = ""
        self._offset = 0
        self._step_interval = step_interval
        self._start_pause = start_pause
        self._loop_pause = loop_pause
        self._pause_remaining = 0.0
        self._separator = separator
        self._loop_length = 0
        self._width_override: Optional[int] = None
        self._timer: Optional[Timer] = None
        self._current_text = ""
        if text:
            self.set_text(text)

    def on_mount(self) -> None:
        self._timer = self.set_interval(self._step_interval, self._tick)
        self._render_frame()

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def on_resize(self, event: events.Resize) -> None:
        self._render_frame()

    def set_text(self, full_text: str) -> None:
        self._full_text = full_text
        self._buffer = ""
        self._offset = 0
        self._pause_remaining = self._start_pause
        self._loop_length = 0
        self._render_frame()

    @property
    def current_text(self) -> str:
        return self._current_text

    @property
    def full_text(self) -> str:
        return self._full_text

    def set_width_override(self, width: Optional[int]) -> None:
        self._width_override = width
        self._render_frame()

    def _available_width(self) -> int:
        if self._width_override is not None:
            return max(0, self._width_override)
        size = getattr(self, "content_size", None) or getattr(self, "size", None)
        return max(0, getattr(size, "width", 0))

    def _build_buffer(self) -> None:
        if not self._full_text:
            self._buffer = ""
            self._loop_length = 0
            return
        self._buffer = f"{self._full_text}{self._separator}{self._full_text}"
        self._loop_length = len(self._full_text) + len(self._separator)

    def _render_frame(self) -> None:
        width = self._available_width()
        if width <= 0 or not self._full_text:
            self._current_text = ""
            self.update("")
            return
        if len(self._full_text) <= width:
            self._current_text = self._full_text
            self.update(self._full_text)
            return
        if not self._buffer:
            self._build_buffer()
        end = self._offset + width
        self._current_text = self._buffer[self._offset : end]
        self.update(self._current_text)

    def _tick(self) -> None:
        width = self._available_width()
        if width <= 0 or not self._full_text:
            self.update("")
            return
        if len(self._full_text) <= width:
            self.update(self._full_text)
            return
        if not self._buffer:
            self._build_buffer()
        if self._pause_remaining > 0:
            self._pause_remaining = max(
                0.0, self._pause_remaining - self._step_interval
            )
            self._render_frame()
            return
        self._offset += 1
        if self._offset >= self._loop_length:
            self._offset = 0
            self._pause_remaining = self._loop_pause
        self._render_frame()
