"""Tests for playlist builder helpers."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer import playlist_builder
from rhythm_slicer.playlist_builder import (
    FileBrowserModel,
    _safe_resolve,
    collect_audio_files,
    list_drives,
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


def test_list_entries_handles_iterdir_errors(tmp_path: Path, monkeypatch) -> None:
    model = FileBrowserModel(tmp_path)
    original_iterdir = Path.iterdir

    def fake_iterdir(self):  # type: ignore[override]
        if self == tmp_path:
            raise OSError("boom")
        return original_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", fake_iterdir)
    entries = model.list_entries()
    assert [entry.name for entry in entries] == [".."]


def test_change_directory_invalid_keeps_selection(tmp_path: Path) -> None:
    model = FileBrowserModel(tmp_path)
    entry = model.list_entries()[0]
    model.toggle_selection(type(entry)(name="x", path=tmp_path / "x.mp3", is_dir=False))
    assert model.selected_paths()
    missing = tmp_path / "missing"
    assert model.change_directory(missing) is False
    assert model.selected_paths()


def test_toggle_selection_skips_parent_entry(tmp_path: Path) -> None:
    model = FileBrowserModel(tmp_path)
    parent = model.list_entries()[0]
    assert parent.is_parent
    assert model.toggle_selection(parent) is False
    assert model.selected_paths() == []


def test_normalize_start_file_and_missing(tmp_path: Path, monkeypatch) -> None:
    audio = tmp_path / "song.mp3"
    audio.write_text("x", encoding="utf-8")
    assert FileBrowserModel._normalize_start(audio) == tmp_path
    monkeypatch.setattr(Path, "cwd", lambda: tmp_path)
    assert FileBrowserModel._normalize_start(tmp_path / "missing") == tmp_path


def test_is_at_root_true() -> None:
    root = Path(Path.cwd().anchor)
    model = FileBrowserModel(root)
    model._current = root
    assert model.is_at_root() is True


def test_collect_audio_files_deduplicates(tmp_path: Path) -> None:
    audio = tmp_path / "song.mp3"
    audio.write_text("x", encoding="utf-8")
    results = collect_audio_files([audio, audio])
    assert results == [audio]


def test_safe_resolve_falls_back(monkeypatch) -> None:
    original_resolve = Path.resolve

    def fake_resolve(self):  # type: ignore[override]
        raise OSError("nope")

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    path = Path("relative.mp3")
    resolved = _safe_resolve(path)
    assert resolved.name == "relative.mp3"
    monkeypatch.setattr(Path, "resolve", original_resolve)


def test_list_drives_windows_branch(monkeypatch) -> None:
    monkeypatch.setattr(playlist_builder.sys, "platform", "win32")

    def fake_exists(self):  # type: ignore[override]
        drive = getattr(self, "drive", "")
        if drive in {"C:", "Z:"}:
            return True
        normalized = str(self).replace("\\", "/")
        return normalized in {"C:", "Z:", "C:/", "Z:/"}

    monkeypatch.setattr(playlist_builder.Path, "exists", fake_exists)
    drives = list_drives()
    assert drives == [Path("C:/"), Path("Z:/")]
