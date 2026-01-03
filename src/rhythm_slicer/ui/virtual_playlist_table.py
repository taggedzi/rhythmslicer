from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Sequence

from rich.text import Text
from textual import active_app, events
from textual.message import Message
from textual.strip import Strip
from textual.widget import Widget

from rhythm_slicer.playlist_store_sqlite import TrackRow
from rhythm_slicer.ui.tui_formatters import ellipsize


@dataclass
class _RowStyle:
    base: str | None
    cursor: str | None = None


class VirtualPlaylistTable(Widget):
    """Virtualized playlist table that renders only visible rows."""

    class CursorMoved(Message):
        def __init__(self, index: int, track_id: int | None) -> None:
            super().__init__()
            self.index = index
            self.track_id = track_id

    class RowSelected(Message):
        def __init__(self, index: int, track_id: int | None) -> None:
            super().__init__()
            self.index = index
            self.track_id = track_id

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
        self.playing_track_id: int | None = None
        self._scroll_offset = 0
        self._last_click_time = 0.0
        self._last_click_index: int | None = None
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

    def reset(self) -> None:
        self._rows_by_index.clear()
        self._index_by_track_id.clear()
        self._total_count = 0
        self.cursor_index = 0
        self.playing_track_id = None
        self._scroll_offset = 0
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

    def set_playing_track_id(self, track_id: int | None) -> None:
        if track_id == self.playing_track_id:
            return
        self.playing_track_id = track_id
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
        self.post_message(
            self.CursorMoved(self.cursor_index, self._track_id_at(self.cursor_index))
        )
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
        if key == "home":
            self.set_cursor_index(0)
            event.stop()
            return
        if key == "end":
            self.set_cursor_index(self._track_count() - 1)
            event.stop()
            return
        if key == "enter":
            self.post_message(
                self.RowSelected(
                    self.cursor_index, self._track_id_at(self.cursor_index)
                )
            )
            event.stop()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if not self._track_count():
            return
        index = self._scroll_offset + event.y
        if 0 <= index < self._track_count():
            self.set_cursor_index(index)
            self.focus()
            now = time.monotonic()
            if self._last_click_index == index and now - self._last_click_time <= 0.4:
                self.post_message(self.RowSelected(index, self._track_id_at(index)))
            self._last_click_index = index
            self._last_click_time = now
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
        if row is None:
            title, artist = self._row_text(None, None, width)
        else:
            title, artist = self._row_text(row, row.has_metadata, width)
        title_width, artist_width = self._column_widths(width)
        title = title.ljust(title_width)
        artist = artist.ljust(artist_width)
        line = f"{title} {artist}"
        style = self._row_style(index)
        text = Text(line, style=style.base or "")
        if style.cursor:
            text.stylize(style.cursor)
        return text

    def _row_text(
        self, row: TrackRow | None, has_metadata: bool | None, width: int
    ) -> tuple[str, str]:
        title_width, artist_width = self._column_widths(width)
        if row is None:
            title = "Loading..."
            artist = "Loading..."
        else:
            title = row.title or row.path.name
            if not has_metadata:
                artist = "Loading..."
            else:
                artist = row.artist or "Unknown"
        return (
            ellipsize(title, title_width),
            ellipsize(artist, artist_width),
        )

    def _column_widths(self, width: int) -> tuple[int, int]:
        if width <= 0:
            return 0, 0
        separator = 1
        usable = max(0, width - separator)
        min_title = 1 if usable > 0 else 0
        min_artist = 1 if usable > 1 else 0
        title_width = max(min_title, int(usable * 0.6))
        artist_width = max(min_artist, usable - title_width)
        total = title_width + artist_width
        if total < usable:
            artist_width += usable - total
        elif total > usable:
            overflow = total - usable
            trim_title = min(overflow, max(0, title_width - min_title))
            title_width -= trim_title
            overflow -= trim_title
            if overflow > 0:
                artist_width = max(min_artist, artist_width - overflow)
        return title_width, artist_width

    def _row_style(self, index: int) -> _RowStyle:
        track_id = self._track_id_at(index)
        if track_id is not None and track_id == self.playing_track_id:
            base = "bold #5fc9d6"
        else:
            base = None
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
            self._scroll_offset = 0
            self._post_scroll_changed()
            return
        self.cursor_index = self._clamp_index(self.cursor_index)

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
