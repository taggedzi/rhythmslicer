"""Tests for playlist builder helpers."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist_builder import (
    FileBrowserModel,
    collect_audio_files,
    reorder_items,
)


def test_browser_entries_sorted_and_parent_first(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "A").mkdir()
    (tmp_path / "z.mp3").write_text("z", encoding="utf-8")
    (tmp_path / "a.flac").write_text("a", encoding="utf-8")
    model = FileBrowserModel(tmp_path)
    names = [entry.name for entry in model.list_entries()]
    assert names[0] == ".."
    assert names[1:3] == ["A", "b"]
    assert names[3:] == ["a.flac", "z.mp3"]


def test_browser_selection_clears_on_directory_change(tmp_path: Path) -> None:
    (tmp_path / "song.mp3").write_text("x", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    model = FileBrowserModel(tmp_path)
    entry = next(entry for entry in model.list_entries() if entry.name == "song.mp3")
    model.toggle_selection(entry)
    assert model.selected_paths()
    model.change_directory(subdir)
    assert model.selected_paths() == []


def test_collect_audio_files_recursive(tmp_path: Path) -> None:
    (tmp_path / "song.mp3").write_text("x", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "loop.wav").write_text("x", encoding="utf-8")
    results = collect_audio_files([tmp_path])
    names = sorted(path.name for path in results)
    assert names == ["loop.wav", "song.mp3"]


def test_reorder_items_up_down() -> None:
    items = ["a", "b", "c", "d"]
    moved_up, selected_up = reorder_items(items, [1, 2], "up")
    assert moved_up == ["b", "c", "a", "d"]
    assert selected_up == [0, 1]
    moved_down, selected_down = reorder_items(items, [1, 2], "down")
    assert moved_down == ["a", "d", "b", "c"]
    assert selected_down == [2, 3]
