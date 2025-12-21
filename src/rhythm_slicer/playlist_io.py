"""Playlist I/O helpers (M3U/M3U8)."""

from __future__ import annotations

from pathlib import Path

from typing import Literal

from rhythm_slicer.metadata import format_display_title, get_track_meta
from rhythm_slicer.playlist import Playlist, Track, SUPPORTED_EXTENSIONS


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def save_m3u8(
    playlist: Playlist,
    dest: Path,
    mode: Literal["relative", "absolute", "auto"] = "relative",
) -> None:
    """Save playlist as UTF-8 M3U8."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U"]
    for track in playlist.tracks:
        path = track.path
        if mode == "absolute":
            lines.append(str(path))
            continue
        try:
            rel = path.relative_to(dest.parent)
        except ValueError:
            rel = None
        if rel is not None:
            lines.append(str(rel))
        else:
            lines.append(str(path))
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_m3u_any(path: Path) -> Playlist:
    """Load an M3U/M3U8 playlist, skipping missing or unsupported files."""
    tracks: list[Track] = []
    base = path.parent
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return Playlist([])
    for line in lines:
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        item = Path(entry)
        if not item.is_absolute():
            item = (base / item).resolve()
        if not item.exists() or not item.is_file():
            continue
        if not _is_supported(item):
            continue
        meta = get_track_meta(item)
        title = format_display_title(item, meta)
        tracks.append(Track(path=item, title=title))
    return Playlist(tracks)
