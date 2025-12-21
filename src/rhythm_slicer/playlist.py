"""Playlist and track modeling for RhythmSlicer."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from rhythm_slicer.metadata import format_display_title, get_track_meta

SUPPORTED_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac"}
M3U_EXTENSIONS = {".m3u", ".m3u8"}


@dataclass(frozen=True)
class Track:
    """Represents a single track."""

    path: Path
    title: str
    duration_ms: Optional[int] = None


class Playlist:
    """A simple playlist with a current index."""

    def __init__(self, tracks: Iterable[Track], index: int = 0, wrap: bool = True):
        self.tracks = list(tracks)
        self.index = index
        self.wrap = wrap
        self.clamp_index()

    def is_empty(self) -> bool:
        return not self.tracks

    def clamp_index(self) -> None:
        if self.is_empty():
            self.index = -1
            return
        self.index = max(0, min(self.index, len(self.tracks) - 1))

    def current(self) -> Optional[Track]:
        if self.is_empty():
            return None
        return self.tracks[self.index]

    def set_index(self, index: int) -> Optional[Track]:
        self.index = index
        self.clamp_index()
        return self.current()

    def next(self) -> Optional[Track]:
        if self.is_empty():
            return None
        if self.wrap:
            self.index = (self.index + 1) % len(self.tracks)
        else:
            if self.index >= len(self.tracks) - 1:
                return None
            self.index += 1
        return self.current()

    def prev(self) -> Optional[Track]:
        if self.is_empty():
            return None
        if self.wrap:
            self.index = (self.index - 1) % len(self.tracks)
        else:
            if self.index <= 0:
                return None
            self.index -= 1
        return self.current()

    def remove(self, index: int) -> None:
        if index < 0 or index >= len(self.tracks):
            return
        del self.tracks[index]
        if self.is_empty():
            self.index = -1
            return
        if index < self.index:
            self.index -= 1
            return
        if index == self.index and self.index >= len(self.tracks):
            self.index = len(self.tracks) - 1


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _track_from_path(path: Path) -> Track:
    meta = get_track_meta(path)
    title = format_display_title(path, meta)
    return Track(path=path, title=title)


def load_from_directory(directory: Path) -> Playlist:
    entries = sorted(p for p in directory.iterdir() if p.is_file())
    tracks = [_track_from_path(path) for path in entries if _is_supported(path)]
    return Playlist(tracks)


def load_from_m3u(m3u_path: Path) -> Playlist:
    from rhythm_slicer.playlist_io import load_m3u_any

    return load_m3u_any(m3u_path)


def load_from_input(path: Path) -> Playlist:
    if path.is_dir():
        return load_from_directory(path)
    if path.suffix.lower() in M3U_EXTENSIONS:
        return load_from_m3u(path)
    if path.is_file() and _is_supported(path):
        return Playlist([_track_from_path(path)])
    return Playlist([])
