"""Playlist helpers for supported audio paths."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_EXTENSIONS = {
    ".mp3",
    ".flac",
    ".wav",
    ".ogg",
    ".m4a",
    ".aac",
    ".opus",
    ".aiff",
    ".aif",
    ".wv",
    ".ape",
    ".mp2",
    ".spx",
    ".m4b",
    ".wma",
    ".amr",
}
M3U_EXTENSIONS = {".m3u", ".m3u8"}


def is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def load_paths_from_directory(directory: Path) -> list[Path]:
    entries = sorted(p for p in directory.iterdir() if p.is_file())
    return [path for path in entries if is_supported(path)]


def load_paths_from_m3u(m3u_path: Path) -> list[Path]:
    from rhythm_slicer.playlist_io import load_m3u_any

    return load_m3u_any(m3u_path)


def load_paths_from_input(path: Path) -> list[Path]:
    if path.is_dir():
        return load_paths_from_directory(path)
    if path.suffix.lower() in M3U_EXTENSIONS:
        return load_paths_from_m3u(path)
    if path.is_file() and is_supported(path):
        return [path]
    return []
