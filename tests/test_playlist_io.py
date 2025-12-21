"""Tests for playlist I/O helpers."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist import Playlist, Track
from rhythm_slicer.playlist_io import load_m3u_any, save_m3u8


def test_round_trip_save_load_preserves_order(tmp_path: Path) -> None:
    track_a = tmp_path / "a.mp3"
    track_b = tmp_path / "b.mp3"
    track_a.write_text("a", encoding="utf-8")
    track_b.write_text("b", encoding="utf-8")
    playlist = Playlist(
        [
            Track(path=track_b, title="b.mp3"),
            Track(path=track_a, title="a.mp3"),
        ]
    )
    dest = tmp_path / "list.m3u8"
    save_m3u8(playlist, dest)
    loaded = load_m3u_any(dest)
    assert [track.path for track in loaded.tracks] == [track_b, track_a]


def test_save_relative_paths(tmp_path: Path) -> None:
    track = tmp_path / "song.mp3"
    track.write_text("x", encoding="utf-8")
    playlist = Playlist([Track(path=track, title="song.mp3")])
    dest = tmp_path / "list.m3u8"
    save_m3u8(playlist, dest)
    lines = dest.read_text(encoding="utf-8").splitlines()
    assert not Path(lines[1]).is_absolute()


def test_load_ignores_comments_and_missing(tmp_path: Path) -> None:
    existing = tmp_path / "keep.mp3"
    existing.write_text("x", encoding="utf-8")
    missing = tmp_path / "missing.mp3"
    m3u = tmp_path / "list.m3u"
    m3u.write_text(
        f"#EXTM3U\n# Comment\n{existing.name}\n{missing.name}\n",
        encoding="utf-8",
    )
    playlist = load_m3u_any(m3u)
    assert [track.path for track in playlist.tracks] == [existing]


def test_save_absolute_paths(tmp_path: Path) -> None:
    track = tmp_path / "song.mp3"
    track.write_text("x", encoding="utf-8")
    playlist = Playlist([Track(path=track, title="song.mp3")])
    dest = tmp_path / "list.m3u8"
    save_m3u8(playlist, dest, mode="absolute")
    lines = dest.read_text(encoding="utf-8").splitlines()
    assert Path(lines[1]).is_absolute()


def test_save_relative_fallback_for_different_root(tmp_path: Path) -> None:
    foreign = Path("Z:/music/track.mp3")
    if foreign.exists() or not foreign.is_absolute():
        return
    playlist = Playlist([Track(path=foreign, title="track.mp3")])
    dest = tmp_path / "list.m3u8"
    save_m3u8(playlist, dest, mode="relative")
    lines = dest.read_text(encoding="utf-8").splitlines()
    assert Path(lines[1]).is_absolute()


def test_round_trip_preserves_paths(tmp_path: Path) -> None:
    track = tmp_path / "song.mp3"
    track.write_text("x", encoding="utf-8")
    playlist = Playlist([Track(path=track, title="song.mp3")])
    dest = tmp_path / "list.m3u8"
    save_m3u8(playlist, dest, mode="absolute")
    loaded = load_m3u_any(dest)
    assert [track.path for track in loaded.tracks] == [track]
