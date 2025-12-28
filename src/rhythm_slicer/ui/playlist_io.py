"""Playlist file helpers for the TUI."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.metadata import format_display_title, get_track_meta
from rhythm_slicer.playlist import Playlist, SUPPORTED_EXTENSIONS, Track


def _load_recursive_directory(path: Path) -> Playlist:
    files = [
        entry
        for entry in path.rglob("*")
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort(key=lambda entry: entry.relative_to(path).as_posix().lower())
    tracks = []
    for entry in files:
        meta = get_track_meta(entry)
        title = format_display_title(entry, meta)
        tracks.append(Track(path=entry, title=title))
    return Playlist(tracks)
