"""Status bar controller for the TUI."""

from __future__ import annotations

from typing import Callable, Optional

from rich.text import Text

from rhythm_slicer.ui.text_helpers import _truncate_line
from rhythm_slicer.ui.tui_types import StatusMessage


class StatusController:
    """Status bar state and rendering."""

    def __init__(self, now: Callable[[], float]) -> None:
        self._now = now
        self._message: Optional[StatusMessage] = None
        self._context: Optional[str] = None

    def show_message(
        self,
        text: str,
        *,
        level: str = "info",
        timeout: Optional[float] = None,
    ) -> None:
        if timeout is None:
            if level == "warn":
                timeout = 6.0
            elif level == "error":
                timeout = 6.0
            else:
                timeout = 3.0
        until = None if timeout == 0 else self._now() + max(0.0, timeout)
        self._message = StatusMessage(text=text, level=level, until=until)

    def clear_message(self) -> None:
        self._message = None

    def set_context(self, name: str) -> None:
        self._context = name

    def render_line(self, width: int, *, focused: object | None = None) -> Text:
        message = self._current_message()
        if message:
            line = _truncate_line(message.text, width)
            style = None
            if message.level == "warn":
                style = "#ffcc66"
            elif message.level == "error":
                style = "#ff5f52"
            return Text(line, style=style) if style else Text(line)
        hint = self._render_hint(focused)
        return Text(_truncate_line(hint, width))

    def _current_message(self) -> Optional[StatusMessage]:
        if not self._message:
            return None
        if self._message.until is None:
            return self._message
        if self._message.until > self._now():
            return self._message
        self._message = None
        return None

    def _render_hint(self, focused: object | None) -> str:
        context = self._context or self._context_from_focus(focused)
        if context == "playlist":
            return "Enter: play  Del: remove  ↑↓: navigate  ?: help"
        if context == "visualizer":
            return "V: change viz  R: restart viz  ?: help"
        if context == "transport":
            return "Space: play/pause  ←/→: seek  ?: help"
        return "Space: play/pause  Enter: play  ?: help"

    def _context_from_focus(self, focused: object | None) -> str:
        if focused is None:
            return "general"
        if isinstance(focused, str):
            focus_id = focused
            if focus_id in {"playlist_list", "playlist_table", "playlist_panel"}:
                return "playlist"
            if focus_id in {
                "visualizer",
                "visualizer_hud",
                "visualizer_panel",
                "track_panel",
                "right_column",
            }:
                return "visualizer"
            if focus_id in {
                "transport_row",
                "key_prev",
                "key_playpause",
                "key_stop",
                "key_next",
            }:
                return "transport"
            return "general"
        if self._focus_has_id(
            focused, {"playlist_list", "playlist_table", "playlist_panel"}
        ):
            return "playlist"
        if self._focus_has_id(
            focused,
            {
                "visualizer",
                "visualizer_hud",
                "visualizer_panel",
                "track_panel",
                "right_column",
            },
        ):
            return "visualizer"
        if self._focus_has_id(
            focused,
            {"transport_row", "key_prev", "key_playpause", "key_stop", "key_next"},
        ):
            return "transport"
        return "general"

    def _focus_has_id(self, widget: object, ids: set[str]) -> bool:
        current = widget
        while current is not None:
            if getattr(current, "id", None) in ids:
                return True
            current = getattr(current, "parent", None)
        return False
