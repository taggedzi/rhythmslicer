from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widget import Widget

from rhythm_slicer.playlist import Track
from rhythm_slicer.ui.text_helpers import _truncate_line


@dataclass
class _RowStyle:
    base: str
    cursor: str | None = None


class VirtualPlaylistList(Widget):
    """Virtualized playlist list that renders only visible rows."""

    class CursorMoved(Message):
        def __init__(self, index: int) -> None:
            super().__init__()
            self.index = index

    def __init__(
        self,
        tracks: Sequence[Track] | None = None,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.can_focus = True
        self._tracks: Sequence[Track] = tracks or []
        self.cursor_index = 0
        self.checked: set[int] = set()
        self.playing_index: int | None = None
        self.filtered_indices: list[int] | None = None
        self._scroll_offset = 0

    def on_mount(self) -> None:
        self._update_virtual_size()

    def on_resize(self) -> None:
        self._update_virtual_size()
        self.refresh()

    def set_tracks(self, tracks: Sequence[Track]) -> None:
        self._tracks = tracks
        self._sanitize_state()
        self._update_virtual_size()
        self.refresh()

    def append_tracks(self, new_tracks: Sequence[Track]) -> None:
        if not new_tracks:
            return
        if not isinstance(self._tracks, list):
            self._tracks = list(self._tracks)
        self._tracks.extend(new_tracks)
        self._sanitize_state()
        self._update_virtual_size()
        self.refresh()

    def notify_data_changed(self) -> None:
        self._sanitize_state()
        self._update_virtual_size()
        self.refresh()

    def set_checked_indices(self, indices: Iterable[int]) -> None:
        count = self._track_count()
        self.checked = {idx for idx in indices if 0 <= idx < count}
        self.refresh()

    def get_checked_indices(self) -> list[int]:
        return sorted(self.checked)

    def clear_checked(self) -> None:
        if not self.checked:
            return
        self.checked.clear()
        self.refresh()

    def check_all(self) -> None:
        count = self._track_count()
        if count <= 0:
            return
        self.checked = set(range(count))
        self.refresh()

    def toggle_checked_at_cursor(self) -> None:
        count = self._track_count()
        if count <= 0:
            return
        index = self._clamp_index(self.cursor_index)
        if index in self.checked:
            self.checked.remove(index)
        else:
            self.checked.add(index)
        self.refresh()

    def set_cursor_index(self, index: int) -> None:
        count = self._track_count()
        if count <= 0:
            self.cursor_index = 0
            return
        clamped = self._clamp_index(index)
        if clamped == self.cursor_index:
            return
        self.cursor_index = clamped
        self._ensure_cursor_visible()
        self.post_message(self.CursorMoved(self.cursor_index))
        self.refresh()

    def on_key(self, event: events.Key) -> None:
        if not self._track_count():
            return
        key = event.key
        if key in {"up", "k"}:
            self._move_cursor(-1)
            event.stop()
            return
        if key in {"down", "j"}:
            self._move_cursor(1)
            event.stop()
            return
        if key == "pageup":
            self._move_cursor(-self.size.height)
            event.stop()
            return
        if key == "pagedown":
            self._move_cursor(self.size.height)
            event.stop()
            return
        if key == "left":
            self._scroll_by(-1)
            event.stop()
            return
        if key == "right":
            self._scroll_by(1)
            event.stop()
            return
        if key == "home":
            self.set_cursor_index(0)
            event.stop()
            return
        if key == "end":
            self.set_cursor_index(self._track_count() - 1)
            event.stop()
            return
        if key == "space":
            self.toggle_checked_at_cursor()
            event.stop()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if not self._track_count():
            return
        index = self._scroll_offset + event.y
        if 0 <= index < self._track_count():
            self.set_cursor_index(index)
            self.focus()
            event.stop()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if not self._track_count():
            return
        self._scroll_by(1)
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if not self._track_count():
            return
        self._scroll_by(-1)
        event.stop()

    def render(self) -> Text:
        height = max(1, self.size.height)
        width = max(1, self.size.width)
        start = self._scroll_offset
        lines: list[Text] = []
        for offset in range(height):
            index = start + offset
            if 0 <= index < self._track_count():
                lines.append(self._render_row(index, width))
            else:
                lines.append(Text(""))
        output = Text()
        for idx, line in enumerate(lines):
            if idx:
                output.append("\n")
            output.append_text(line)
        return output

    def _render_row(self, index: int, width: int) -> Text:
        track = self._tracks[index]
        count_width = max(2, len(str(self._track_count() or 1)))
        marker = "[x]" if index in self.checked else "[ ]"
        playing = "▶" if self.playing_index == index else " "
        title = track.title or track.path.name
        line = f"{playing} {marker} {index + 1:>{count_width}d} {title}"
        line = _truncate_line(line, width)
        style = self._row_style(index)
        text = Text(line, style=style.base)
        if style.cursor:
            text.stylize(style.cursor)
        return text

    def _row_style(self, index: int) -> _RowStyle:
        base = "#5fc9d6" if index in self.checked else "#c6d0f2"
        if index == self.cursor_index and self.has_focus:
            return _RowStyle(base=base, cursor="reverse")
        return _RowStyle(base=base)

    def _track_count(self) -> int:
        return len(self._tracks)

    def _sanitize_state(self) -> None:
        count = self._track_count()
        if count <= 0:
            self.cursor_index = 0
            self.checked.clear()
            return
        self.cursor_index = self._clamp_index(self.cursor_index)
        self.checked = {idx for idx in self.checked if 0 <= idx < count}

    def _update_virtual_size(self) -> None:
        height = max(1, self._track_count())
        self.virtual_size = self.size.with_height(height)
        self._clamp_scroll_offset()

    def _ensure_cursor_visible(self) -> None:
        height = max(1, self.size.height)
        top = self._scroll_offset
        bottom = top + height - 1
        if self.cursor_index < top:
            self._scroll_offset = self.cursor_index
        elif self.cursor_index > bottom:
            target = max(0, self.cursor_index - height + 1)
            self._scroll_offset = target
        self._clamp_scroll_offset()

    def _move_cursor(self, delta: int) -> None:
        self.set_cursor_index(self.cursor_index + delta)

    def _clamp_index(self, index: int) -> int:
        count = self._track_count()
        if count <= 0:
            return 0
        return max(0, min(index, count - 1))

    def _scroll_by(self, delta: int) -> None:
        self._scroll_offset += delta
        self._clamp_scroll_offset()
        self.refresh()

    def _clamp_scroll_offset(self) -> None:
        height = max(1, self.size.height)
        max_offset = max(0, self._track_count() - height)
        if self._scroll_offset < 0:
            self._scroll_offset = 0
        elif self._scroll_offset > max_offset:
            self._scroll_offset = max_offset

    @property
    def scroll_offset(self) -> int:
        return self._scroll_offset
