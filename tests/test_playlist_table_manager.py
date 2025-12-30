from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rich.text import Text
from textual.widgets.data_table import RowDoesNotExist

from rhythm_slicer.metadata import TrackMeta
from rhythm_slicer.playlist import Playlist, Track
from rhythm_slicer.ui.playlist_table_manager import PlaylistTableManager


@dataclass
class _Size:
    width: int


class _Table:
    def __init__(self, width: int = 40) -> None:
        self.content_size = _Size(width)
        self.columns: dict[str, dict[str, int | None]] = {}
        self.rows: dict[str, dict[str, Text]] = {}
        self.row_keys: list[str] = []
        self.cursor_row = 0
        self.cursor_type = None
        self.show_cursor = False
        self.zebra_stripes = True
        self.update_calls: list[tuple[str, str, Text]] = []

    @property
    def row_count(self) -> int:
        return len(self.row_keys)

    def clear(self, *, columns: bool = False) -> None:
        self.rows.clear()
        self.row_keys.clear()
        if columns:
            self.columns.clear()

    def add_column(self, name: str, *, key: str, width: int | None = None) -> None:
        self.columns[key] = {"name": name, "width": width}

    def add_row(self, title: Text, artist: Text, *, key: str) -> None:
        self.rows[key] = {"title": title, "artist": artist}
        self.row_keys.append(key)

    def update_cell(self, row_key: str, column_key: str, value: Text) -> None:
        if row_key not in self.rows:
            raise RowDoesNotExist(row_key)
        self.rows[row_key][column_key] = value
        self.update_calls.append((row_key, column_key, value))

    def move_cursor(self, *, row: int, column: int, scroll: bool = False) -> None:
        self.cursor_row = row

    def get_row_index(self, row_key: str) -> int:
        if row_key not in self.row_keys:
            raise RowDoesNotExist(row_key)
        return self.row_keys.index(row_key)


class _App:
    def __init__(self, table: _Table | None) -> None:
        self._playlist_table = table
        self._playlist_title_column = "title"
        self._playlist_artist_column = "artist"
        self._playlist_table_width = 0
        self._playlist_title_max = 0
        self._playlist_artist_max = 0
        self._playlist_table_source = None
        self._playing_key = None
        self._selected_key = None
        self._missing_row_keys_logged: set[str] = set()
        self._playing_index: int | None = 0
        self._suppress_table_events = False
        self.playlist: Playlist | None = None
        self._update_calls = 0
        self._sync_calls = 0
        self._timer_calls: list[tuple[float, object]] = []
        self._meta_map: dict[Path, TrackMeta] = {}
        self._ensure_calls: list[Path] = []

    def _get_track_meta_cached(self, path: Path) -> TrackMeta | None:
        return self._meta_map.get(path)

    def _ensure_track_meta_loaded(self, path: Path) -> None:
        self._ensure_calls.append(path)

    def _update_playlist_view(self) -> None:
        self._update_calls += 1

    def _sync_play_order_pos(self) -> None:
        self._sync_calls += 1

    def set_timer(self, delay: float, callback) -> None:
        self._timer_calls.append((delay, callback))


def _make_playlist() -> Playlist:
    tracks = [
        Track(path=Path("one.mp3"), title="one"),
        Track(path=Path("two.mp3"), title="two"),
    ]
    return Playlist(tracks)


def test_init_playlist_table_sets_columns() -> None:
    table = _Table(width=40)
    app = _App(table)
    manager = PlaylistTableManager(app)

    manager._init_playlist_table()

    assert set(table.columns) == {"title", "artist"}
    assert table.cursor_type == "row"
    assert table.show_cursor is True
    assert table.zebra_stripes is False


def test_init_playlist_table_skips_without_table() -> None:
    app = _App(None)
    manager = PlaylistTableManager(app)

    manager._init_playlist_table()

    assert app._playlist_table is None


def test_playlist_table_content_width() -> None:
    app = _App(None)
    manager = PlaylistTableManager(app)
    assert manager._playlist_table_content_width() == 0
    table = _Table(width=22)
    app._playlist_table = table
    assert manager._playlist_table_content_width() == 22


def test_playlist_table_limits_basic() -> None:
    table = _Table(width=50)
    app = _App(table)
    manager = PlaylistTableManager(app)

    width, title_max, artist_max = manager._playlist_table_limits()

    assert width == 50
    assert title_max == 26
    assert artist_max == 18


def test_playlist_table_limits_with_fallback_width() -> None:
    table = _Table(width=0)
    app = _App(table)
    app._playlist_table_width = 30
    manager = PlaylistTableManager(app)

    width, title_max, artist_max = manager._playlist_table_limits()

    assert width == 30
    assert title_max > 0
    assert artist_max > 0


def test_refresh_after_layout_schedules_when_width_zero() -> None:
    table = _Table(width=0)
    app = _App(table)
    manager = PlaylistTableManager(app)

    manager._refresh_playlist_table_after_layout()

    assert app._timer_calls
    assert app._timer_calls[0][0] == 0.05


def test_playlist_row_cells_with_meta_and_style() -> None:
    table = _Table(width=40)
    app = _App(table)
    manager = PlaylistTableManager(app)
    track = Track(path=Path("song.mp3"), title="Fallback")
    app._meta_map[track.path] = TrackMeta(artist="Artist", title="LongTitle")

    title_cell, artist_cell = manager._playlist_row_cells(
        track, is_playing=True, title_max=5, artist_max=6
    )

    assert title_cell.plain == "Lo..."
    assert artist_cell.plain == "Artist"
    assert title_cell.style == "bold #5fc9d6"


def test_playlist_row_cells_triggers_meta_load() -> None:
    table = _Table(width=40)
    app = _App(table)
    manager = PlaylistTableManager(app)
    track = Track(path=Path("song.mp3"), title="Fallback")

    manager._playlist_row_cells(track, is_playing=False, title_max=10, artist_max=10)

    assert app._ensure_calls == [track.path]


def test_refresh_playlist_table_rebuilds_rows() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = _make_playlist()
    app._playing_index = 1
    app._selected_key = "0"
    manager = PlaylistTableManager(app)

    manager._refresh_playlist_table(rebuild=True)

    assert table.row_count == 2
    assert app._playing_key == "1"
    assert table.cursor_row == 0


def test_refresh_playlist_table_width_changed_updates_cells() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = _make_playlist()
    manager = PlaylistTableManager(app)
    manager._refresh_playlist_table(rebuild=True)
    old_title_width = table.columns["title"]["width"]
    old_artist_width = table.columns["artist"]["width"]
    table.content_size = _Size(50)

    manager._refresh_playlist_table(rebuild=False)

    assert table.row_count == 2
    assert app._playlist_table_width == 50
    assert table.columns["title"]["width"] != old_title_width
    assert table.columns["artist"]["width"] != old_artist_width


def test_update_playing_row_style_updates_cells() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = _make_playlist()
    app._playing_index = 0
    manager = PlaylistTableManager(app)
    manager._refresh_playlist_table(rebuild=True)
    app._playing_index = 1

    manager._update_playing_row_style()

    assert len(table.update_calls) == 4
    assert app._playing_key == "1"


def test_update_playing_row_style_no_playlist() -> None:
    table = _Table(width=40)
    app = _App(table)
    manager = PlaylistTableManager(app)

    manager._update_playing_row_style()

    assert table.update_calls == []


def test_update_playing_row_style_same_key_short_circuits() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = _make_playlist()
    app._playing_index = 0
    manager = PlaylistTableManager(app)
    manager._refresh_playlist_table(rebuild=True)

    manager._update_playing_row_style()

    assert table.update_calls == []


def test_update_playing_row_style_handles_bad_keys() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = _make_playlist()
    manager = PlaylistTableManager(app)
    manager._refresh_playlist_table(rebuild=True)
    app._playing_index = "bad"  # type: ignore[assignment]
    app._playing_key = "0"

    manager._update_playing_row_style()

    assert app._playing_key == "bad"


def test_update_row_cells_missing_logs_once() -> None:
    table = _Table(width=40)
    app = _App(table)
    manager = PlaylistTableManager(app)

    result = manager._update_row_cells("missing", Text("a"), Text("b"))

    assert result is False
    assert "missing" in app._missing_row_keys_logged
    result = manager._update_row_cells("missing", Text("a"), Text("b"))
    assert result is False
    assert len(app._missing_row_keys_logged) == 1


def test_update_row_cells_without_table() -> None:
    app = _App(None)
    manager = PlaylistTableManager(app)

    result = manager._update_row_cells("missing", Text("a"), Text("b"))

    assert result is False


def test_move_table_cursor_noop_when_same_row() -> None:
    table = _Table(width=40)
    app = _App(table)
    manager = PlaylistTableManager(app)
    table.cursor_row = 1

    manager._move_table_cursor(1)

    assert app._suppress_table_events is False


def test_set_selected_clamps_and_moves_cursor() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = _make_playlist()
    manager = PlaylistTableManager(app)

    manager._set_selected(10)

    assert app.playlist.index == 1
    assert app._selected_key == "1"
    assert table.cursor_row == 1
    assert app._sync_calls == 1
    assert app._update_calls == 1


def test_set_selected_noop_when_empty() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = Playlist([])
    manager = PlaylistTableManager(app)

    manager._set_selected(1)

    assert app._update_calls == 0


def test_restore_table_cursor_missing_key_logs() -> None:
    table = _Table(width=40)
    app = _App(table)
    app._selected_key = "missing"
    manager = PlaylistTableManager(app)

    manager._restore_table_cursor_from_selected()

    assert "missing" in app._missing_row_keys_logged


def test_refresh_playlist_table_empty_playlist_clears() -> None:
    table = _Table(width=40)
    app = _App(table)
    app.playlist = Playlist([])
    manager = PlaylistTableManager(app)
    table.row_keys = ["0"]

    manager._refresh_playlist_table(rebuild=False)

    assert table.row_count == 0
    assert app._playing_key is None
    assert app._selected_key is None
