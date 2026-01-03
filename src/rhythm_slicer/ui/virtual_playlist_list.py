from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from rich.text import Text
from textual import active_app
from textual.strip import Strip
from textual import events
from textual.message import Message
from textual.widget import Widget

from rhythm_slicer.playlist_store_sqlite import TrackRow
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
        rows: Sequence[TrackRow] | None = None,
        *,
        id: str | None = None,
    ) -> None:
        super().__init__(id=id)
        self.can_focus = True
        self._rows_by_index: dict[int, TrackRow] = {}
        self._index_by_track_id: dict[int, int] = {}
        self._total_count = 0
        self.cursor_index = 0
        self.checked_track_ids: set[int] = set()
        self.playing_track_id: int | None = None
        self.filtered_indices: list[int] | None = None
        self._scroll_offset = 0
        if rows:
            self.set_tracks(rows)

    def on_mount(self) -> None:
        self.styles.height = "1fr"
        self.styles.overflow_y = "hidden"
        self._clamp_scroll_offset()
        self._post_scroll_changed()

    def on_resize(self) -> None:
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def set_tracks(self, rows: Sequence[TrackRow]) -> None:
        self._rows_by_index = {idx: row for idx, row in enumerate(rows)}
        self._index_by_track_id = {row.track_id: idx for idx, row in enumerate(rows)}
        self._total_count = len(rows)
        self._sanitize_state()
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def set_total_count(self, total: int) -> None:
        self._total_count = max(0, total)
        self._sanitize_state()
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def set_rows(self, offset: int, rows: Sequence[TrackRow]) -> None:
        for idx, row in enumerate(rows):
            absolute = offset + idx
            self._rows_by_index[absolute] = row
            self._index_by_track_id[row.track_id] = absolute
        self._sanitize_state()
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def update_row(self, track_id: int, row: TrackRow) -> None:
        index = self._index_by_track_id.get(track_id)
        if index is None:
            return
        self._rows_by_index[index] = row
        self.refresh()

    def notify_data_changed(self) -> None:
        self._sanitize_state()
        self._clamp_scroll_offset()
        self._post_scroll_changed()
        self.refresh()

    def set_checked_track_ids(self, track_ids: Iterable[int]) -> None:
        self.checked_track_ids = {track_id for track_id in track_ids}
        self.refresh()

    def get_checked_track_ids(self) -> list[int]:
        return sorted(self.checked_track_ids)

    def clear_checked(self) -> None:
        if not self.checked_track_ids:
            return
        self.checked_track_ids.clear()
        self.refresh()

    def check_all(self) -> None:
        if not self._index_by_track_id:
            return
        self.checked_track_ids = set(self._index_by_track_id.keys())
        self.refresh()

    def get_visible_indices(self) -> list[int]:
        if not self._track_count():
            return []
        height = self._viewport_height()
        start = self._scroll_offset
        end = min(self._track_count(), start + height)
        return list(range(start, end))

    def view_info(self) -> tuple[int, int, int]:
        return self._scroll_offset, self._track_count(), self._viewport_height()

    def get_cached_row(self, index: int) -> TrackRow | None:
        return self._rows_by_index.get(index)

    def toggle_checked_at_cursor(self) -> None:
        count = self._track_count()
        if count <= 0:
            return
        index = self._clamp_index(self.cursor_index)
        track_id = self._track_id_at(index)
        if track_id is None:
            return
        if track_id in self.checked_track_ids:
            self.checked_track_ids.remove(track_id)
        else:
            self.checked_track_ids.add(track_id)
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
        row = self._rows_by_index.get(index)
        count_width = max(2, len(str(self._track_count() or 1)))
        track_id = row.track_id if row else None
        marker = "[x]" if track_id in self.checked_track_ids else "[ ]"
        playing = "▶" if track_id == self.playing_track_id else " "
        if row is None:
            title = "Loading..."
        else:
            title = row.title or row.path.name
        line = f"{playing} {marker} {index + 1:>{count_width}d} {title}"
        line = _truncate_line(line, width)
        style = self._row_style(index)
        text = Text(line, style=style.base)
        if style.cursor:
            text.stylize(style.cursor)
        return text

    def _row_style(self, index: int) -> _RowStyle:
        track_id = self._track_id_at(index)
        base = "#5fc9d6" if track_id in self.checked_track_ids else "#c6d0f2"
        if index == self.cursor_index and self.has_focus:
            return _RowStyle(base=base, cursor="reverse")
        return _RowStyle(base=base)

    def _track_count(self) -> int:
        return self._total_count

    def _track_id_at(self, index: int) -> int | None:
        row = self._rows_by_index.get(index)
        return row.track_id if row else None

    def _sanitize_state(self) -> None:
        count = self._track_count()
        if count <= 0:
            self.cursor_index = 0
            self.checked_track_ids.clear()
            self._scroll_offset = 0
            self._post_scroll_changed()
            return
        self.cursor_index = self._clamp_index(self.cursor_index)
        self.checked_track_ids = set(self.checked_track_ids)
        if self._total_count == len(self._rows_by_index):
            self.checked_track_ids.intersection_update(self._index_by_track_id.keys())

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
