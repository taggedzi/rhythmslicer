"""Playlist I/O helpers (M3U/M3U8)."""

from __future__ import annotations

from pathlib import Path

from typing import Iterable, Literal

from rhythm_slicer.playlist import SUPPORTED_EXTENSIONS


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def save_m3u8(
    paths: Iterable[Path],
    dest: Path,
    mode: Literal["relative", "absolute", "auto"] = "relative",
) -> None:
    """Save playlist as UTF-8 M3U8."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U"]
    for path in paths:
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


def load_m3u_any(path: Path) -> list[Path]:
    """Load an M3U/M3U8 playlist, skipping missing or unsupported files."""
    tracks: list[Path] = []
    base = path.parent
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
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
        tracks.append(item)
    return tracks
