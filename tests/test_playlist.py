"""Tests for playlist path loading."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist import (
    load_paths_from_directory,
    load_paths_from_input,
    load_paths_from_m3u,
)


def test_directory_load_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.mp3").write_text("b", encoding="utf-8")
    (tmp_path / "a.flac").write_text("a", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    paths = load_paths_from_directory(tmp_path)
    assert [path.name for path in paths] == ["a.flac", "b.mp3"]


def test_m3u_parsing_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "one.mp3").write_text("1", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "two.wav").write_text("2", encoding="utf-8")
    m3u = tmp_path / "list.m3u"
    m3u.write_text("#EXTM3U\n# Comment line\none.mp3\nsub/two.wav\n", encoding="utf-8")
    playlist = load_paths_from_m3u(m3u)
    assert [path.name for path in playlist] == ["one.mp3", "two.wav"]


def test_load_from_input_file_and_unsupported(tmp_path: Path) -> None:
    supported = tmp_path / "song.mp3"
    supported.write_text("x", encoding="utf-8")
    playlist = load_paths_from_input(supported)
    assert playlist == [supported]
    unsupported = tmp_path / "note.txt"
    unsupported.write_text("x", encoding="utf-8")
    empty = load_paths_from_input(unsupported)
    assert empty == []
