"""Unit tests for VirtualPlaylistList state handling."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist import Track
from rhythm_slicer.ui.virtual_playlist_list import VirtualPlaylistList


def _track(path: Path) -> Track:
    return Track(path=path, title=path.name)


def test_virtual_playlist_list_check_all_and_clear(tmp_path: Path) -> None:
    tracks = [_track(tmp_path / f"{idx}.mp3") for idx in range(3)]
    widget = VirtualPlaylistList(tracks)
    widget.check_all()
    assert widget.get_checked_indices() == [0, 1, 2]
    widget.clear_checked()
    assert widget.get_checked_indices() == []


def test_virtual_playlist_list_toggle_checked_at_cursor(tmp_path: Path) -> None:
    tracks = [_track(tmp_path / "a.mp3"), _track(tmp_path / "b.mp3")]
    widget = VirtualPlaylistList(tracks)
    widget.cursor_index = 1
    widget.toggle_checked_at_cursor()
    assert widget.get_checked_indices() == [1]
    widget.toggle_checked_at_cursor()
    assert widget.get_checked_indices() == []


def test_virtual_playlist_list_cursor_clamps_on_set_tracks(tmp_path: Path) -> None:
    tracks = [_track(tmp_path / f"{idx}.mp3") for idx in range(4)]
    widget = VirtualPlaylistList(tracks)
    widget.cursor_index = 3
    widget.set_tracks(tracks[:2])
    assert widget.cursor_index == 1


def test_virtual_playlist_list_checked_clamps_on_set_tracks(tmp_path: Path) -> None:
    tracks = [_track(tmp_path / f"{idx}.mp3") for idx in range(4)]
    widget = VirtualPlaylistList(tracks)
    widget.set_checked_indices({1, 3})
    widget.set_tracks(tracks[:2])
    assert widget.get_checked_indices() == [1]


def test_virtual_playlist_list_no_row_widgets_created(tmp_path: Path) -> None:
    tracks = [_track(tmp_path / f"{idx}.mp3") for idx in range(10)]
    widget = VirtualPlaylistList(tracks)
    assert list(widget.children) == []
