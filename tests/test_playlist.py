"""Tests for playlist loading and navigation."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist import Playlist, Track, load_from_directory, load_from_m3u


def test_directory_load_sorted(tmp_path: Path) -> None:
    (tmp_path / "b.mp3").write_text("b", encoding="utf-8")
    (tmp_path / "a.flac").write_text("a", encoding="utf-8")
    (tmp_path / "c.txt").write_text("c", encoding="utf-8")
    playlist = load_from_directory(tmp_path)
    titles = [track.title for track in playlist.tracks]
    assert titles == ["a.flac", "b.mp3"]


def test_m3u_parsing_relative_paths(tmp_path: Path) -> None:
    (tmp_path / "one.mp3").write_text("1", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "two.wav").write_text("2", encoding="utf-8")
    m3u = tmp_path / "list.m3u"
    m3u.write_text(
        "#EXTM3U\n# Comment line\none.mp3\nsub/two.wav\n", encoding="utf-8"
    )
    playlist = load_from_m3u(m3u)
    titles = [track.title for track in playlist.tracks]
    assert titles == ["one.mp3", "two.wav"]


def test_playlist_wrap_next_prev() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
    ]
    playlist = Playlist(tracks)
    assert playlist.current() == tracks[0]
    playlist.next()
    assert playlist.current() == tracks[1]
    playlist.next()
    assert playlist.current() == tracks[0]
    playlist.prev()
    assert playlist.current() == tracks[1]
