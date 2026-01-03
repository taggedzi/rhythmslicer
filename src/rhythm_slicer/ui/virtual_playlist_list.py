from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from rich.text import Text
from textual import active_app
from textual.strip import Strip
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

    class ScrollChanged(Message):
        bubble = True

        def __init__(self, *, offset: int, total: int, viewport: int) -> None:
            super().__init__()
            self.offset = offset
            self.total = total
            self.viewport = viewport

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
        self._title_overrides: dict[Path, str] = {}
        self._scroll_offset = 0

    def on_mount(self) -> None:
        self.styles.height = "1fr"
        self.styles.overflow_y = "hidden"
        self._clamp_scroll_offset()
        self._post_scroll_changed()

    def on_resize(self) -> None:
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def set_tracks(self, tracks: Sequence[Track]) -> None:
        self._tracks = tracks
        self._sanitize_state()
        self._prune_title_overrides()
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def append_tracks(self, new_tracks: Sequence[Track]) -> None:
        if not new_tracks:
            return
        if not isinstance(self._tracks, list):
            self._tracks = list(self._tracks)
        self._tracks.extend(new_tracks)
        self._sanitize_state()
        self._prune_title_overrides()
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def notify_data_changed(self) -> None:
        self._sanitize_state()
        self._prune_title_overrides()
        self._clamp_scroll_offset()
        self._post_scroll_changed()
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

    def get_visible_indices(self) -> list[int]:
        if not self._track_count():
            return []
        height = self._viewport_height()
        start = self._scroll_offset
        end = min(self._track_count(), start + height)
        return list(range(start, end))

    def set_title_override(self, path: Path, title: str) -> None:
        if not title:
            return
        self._title_overrides[path] = title
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
            self._scroll_offset = 0
            self._post_scroll_changed()
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

    def render_line(self, y: int) -> Strip:
        width = max(1, self.size.width)
        start = self._scroll_offset
        index = start + y
        if 0 <= index < self._track_count():
            line = self._render_row(index, width)
        else:
            line = Text("")
        app = active_app.get()
        segments = list(line.render(app.console))
        return Strip(segments)

    def _render_row(self, index: int, width: int) -> Text:
        track = self._tracks[index]
        count_width = max(2, len(str(self._track_count() or 1)))
        marker = "[x]" if index in self.checked else "[ ]"
        playing = "▶" if self.playing_index == index else " "
        title = self._title_overrides.get(track.path) or track.title or track.path.name
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
            self._scroll_offset = 0
            self._post_scroll_changed()
            return
        self.cursor_index = self._clamp_index(self.cursor_index)
        self.checked = {idx for idx in self.checked if 0 <= idx < count}
        self._prune_title_overrides()

    def _ensure_cursor_visible(self) -> None:
        height = self._viewport_height()
        top = self._scroll_offset
        bottom = top + height - 1
        if self.cursor_index < top:
            self._scroll_to_offset(self.cursor_index)
        elif self.cursor_index > bottom:
            target = max(0, self.cursor_index - height + 1)
            self._scroll_to_offset(target)

    def _move_cursor(self, delta: int) -> None:
        self.set_cursor_index(self.cursor_index + delta)

    def _clamp_index(self, index: int) -> int:
        count = self._track_count()
        if count <= 0:
            return 0
        return max(0, min(index, count - 1))

    def _scroll_by(self, delta: int) -> None:
        self._scroll_to_offset(self._scroll_offset + delta)

    def set_scroll_offset(self, offset: int) -> None:
        self._scroll_to_offset(offset)

    def _scroll_to_offset(self, value: int) -> None:
        target = max(0, min(value, self._max_scroll_offset()))
        if target == self._scroll_offset:
            return
        self._scroll_offset = target
        self._post_scroll_changed()
        self.refresh()

    def _max_scroll_offset(self) -> int:
        count = self._track_count()
        height = self._viewport_height()
        return max(0, count - height)

    def _viewport_height(self) -> int:
        return max(1, self.size.height)

    def _clamp_scroll_offset(self) -> None:
        self._scroll_offset = min(
            max(0, self._scroll_offset), self._max_scroll_offset()
        )

    def _post_scroll_changed(self) -> None:
        if not self.is_mounted:
            return
        self.post_message(
            self.ScrollChanged(
                offset=self._scroll_offset,
                total=self._track_count(),
                viewport=self._viewport_height(),
            )
        )

    def _prune_title_overrides(self) -> None:
        if not self._title_overrides:
            return
        paths = {track.path for track in self._tracks}
        self._title_overrides = {
            path: title
            for path, title in self._title_overrides.items()
            if path in paths
        }


class VirtualPlaylistScrollbar(Widget):
    """Minimal vertical scrollbar for the virtual playlist list."""

    class ScrollRequested(Message):
        bubble = True

        def __init__(self, offset: int) -> None:
            super().__init__()
            self.offset = offset

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.can_focus = False
        self._total = 0
        self._offset = 0
        self._viewport = 1

    def set_state(self, *, total: int, offset: int, viewport: int) -> None:
        self._total = max(0, total)
        self._viewport = max(1, viewport)
        self._offset = max(0, min(offset, self._max_offset()))
        self.refresh()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if self._total <= self._viewport:
            return
        target = self._offset_from_y(event.y)
        self.post_message(self.ScrollRequested(target))
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if self._total <= self._viewport:
            return
        self.post_message(self.ScrollRequested(self._offset - 1))
        event.stop()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if self._total <= self._viewport:
            return
        self.post_message(self.ScrollRequested(self._offset + 1))
        event.stop()

    def render_line(self, y: int) -> Strip:
        height = max(1, self.size.height)
        thumb_top, thumb_bottom = self._thumb_range(height)
        char = "#" if thumb_top <= y < thumb_bottom else "|"
        text = Text(char)
        app = active_app.get()
        segments = list(text.render(app.console))
        return Strip(segments)

    def _thumb_range(self, height: int) -> tuple[int, int]:
        if self._total <= self._viewport:
            return 0, height
        max_offset = self._max_offset()
        thumb_height = max(1, int(round(height * height / self._total)))
        thumb_height = min(height, thumb_height)
        available = max(1, height - thumb_height)
        top = int(round(self._offset * available / max_offset))
        return top, top + thumb_height

    def _offset_from_y(self, y: int) -> int:
        height = max(1, self.size.height)
        if self._total <= self._viewport:
            return 0
        max_offset = self._max_offset()
        if height <= 1:
            return 0
        ratio = max(0.0, min(1.0, y / (height - 1)))
        return int(round(ratio * max_offset))

    def _max_offset(self) -> int:
        return max(0, self._total - self._viewport)
