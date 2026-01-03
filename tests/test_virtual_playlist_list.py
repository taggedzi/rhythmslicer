"""Unit tests for VirtualPlaylistList state handling."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist_store_sqlite import TrackRow
from rhythm_slicer.ui.virtual_playlist_list import VirtualPlaylistList


def _row(track_id: int, path: Path) -> TrackRow:
    return TrackRow(
        track_id=track_id,
        path=path,
        title=path.name,
        artist=None,
        album=None,
        duration_seconds=None,
        has_metadata=False,
    )


def test_virtual_playlist_list_check_all_and_clear(tmp_path: Path) -> None:
    rows = [_row(idx + 1, tmp_path / f"{idx}.mp3") for idx in range(3)]
    widget = VirtualPlaylistList(rows)
    widget.check_all()
    assert widget.get_checked_track_ids() == [1, 2, 3]
    widget.clear_checked()
    assert widget.get_checked_track_ids() == []


def test_virtual_playlist_list_toggle_checked_at_cursor(tmp_path: Path) -> None:
    rows = [_row(1, tmp_path / "a.mp3"), _row(2, tmp_path / "b.mp3")]
    widget = VirtualPlaylistList(rows)
    widget.cursor_index = 1
    widget.toggle_checked_at_cursor()
    assert widget.get_checked_track_ids() == [2]
    widget.toggle_checked_at_cursor()
    assert widget.get_checked_track_ids() == []


def test_virtual_playlist_list_cursor_clamps_on_set_tracks(tmp_path: Path) -> None:
    rows = [_row(idx + 1, tmp_path / f"{idx}.mp3") for idx in range(4)]
    widget = VirtualPlaylistList(rows)
    widget.cursor_index = 3
    widget.set_tracks(rows[:2])
    assert widget.cursor_index == 1


def test_virtual_playlist_list_checked_clamps_on_set_tracks(tmp_path: Path) -> None:
    rows = [_row(idx + 1, tmp_path / f"{idx}.mp3") for idx in range(4)]
    widget = VirtualPlaylistList(rows)
    widget.set_checked_track_ids({2, 4})
    widget.set_tracks(rows[:2])
    assert widget.get_checked_track_ids() == [2]


def test_virtual_playlist_list_no_row_widgets_created(tmp_path: Path) -> None:
    rows = [_row(idx + 1, tmp_path / f"{idx}.mp3") for idx in range(10)]
    widget = VirtualPlaylistList(rows)
    assert list(widget.children) == []
