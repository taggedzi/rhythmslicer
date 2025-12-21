"""Tests for metadata formatting and parsing."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

from rhythm_slicer import metadata
from rhythm_slicer.metadata import TrackMeta, format_display_title, read_track_meta


def test_format_display_title_artist_and_title() -> None:
    path = Path("song.mp3")
    meta = TrackMeta(artist="Artist", title="Title")
    assert format_display_title(path, meta) == "Artist – Title"


def test_format_display_title_title_only() -> None:
    path = Path("song.mp3")
    meta = TrackMeta(artist=None, title="Title")
    assert format_display_title(path, meta) == "Title"


def test_format_display_title_fallback_filename() -> None:
    path = Path("song.mp3")
    meta = TrackMeta(artist=None, title=None)
    assert format_display_title(path, meta) == "song.mp3"


def test_read_track_meta_with_mocked_mutagen(tmp_path: Path, monkeypatch) -> None:
    class FakeAudio:
        def __init__(self, tags: dict[str, object]):
            self.tags = tags

    def fake_file(path: Path) -> FakeAudio:
        return FakeAudio({"artist": ["Artist"], "title": ["Title"]})

    monkeypatch.setitem(sys.modules, "mutagen", SimpleNamespace(File=fake_file))
    meta = read_track_meta(tmp_path / "song.mp3")
    assert meta.artist == "Artist"
    assert meta.title == "Title"


def test_read_track_meta_handles_unsupported(tmp_path: Path, monkeypatch) -> None:
    def fake_file(path: Path) -> None:
        return None

    monkeypatch.setitem(sys.modules, "mutagen", SimpleNamespace(File=fake_file))
    meta = read_track_meta(tmp_path / "song.mp3")
    assert meta.artist is None
    assert meta.title is None


def test_extract_text_and_read_tag_helpers() -> None:
    class _TextValue:
        def __init__(self, value: object, *, raises: bool = False) -> None:
            self._value = value
            self._raises = raises

        @property
        def text(self) -> object:
            if self._raises:
                raise RuntimeError("boom")
            return self._value

        def __str__(self) -> str:
            return "fallback"

    class _Tags:
        def __init__(self, mapping: dict[str, object]) -> None:
            self._mapping = mapping

        def get(self, key: str) -> object:
            return self._mapping.get(key)

    assert metadata._extract_text(b"  hi ") == "hi"
    assert metadata._extract_text(["  yo "]) == "yo"
    assert metadata._extract_text(_TextValue(" ok ")) == "ok"
    tags = _Tags({"artist": ["Artist"]})
    assert metadata._read_tag(tags, ("missing", "artist")) == "Artist"
