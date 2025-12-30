"""Tests for playlist file picker helpers."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.ui.playlist_file_picker import (
    filter_playlist_filenames,
    pick_start_directory,
)


def test_filter_playlist_filenames() -> None:
    names = ["mix.m3u", "mix.m3u8", "track.mp3", "README.M3U", "notes.txt"]
    assert filter_playlist_filenames(names) == ["mix.m3u", "mix.m3u8", "README.M3U"]


def test_pick_start_directory_uses_last_parent(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    playlist_dir.mkdir()
    last_path = playlist_dir / "set.m3u8"
    last_path.write_text("x", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    assert pick_start_directory(last_path, cwd) == playlist_dir


def test_pick_start_directory_uses_last_dir(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    playlist_dir.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    assert pick_start_directory(playlist_dir, cwd) == playlist_dir


def test_pick_start_directory_falls_back_to_cwd(tmp_path: Path) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    missing = tmp_path / "missing" / "list.m3u"
    assert pick_start_directory(missing, cwd) == cwd
