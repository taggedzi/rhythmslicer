"""Playlist file helpers for the TUI."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist import SUPPORTED_EXTENSIONS


def _load_recursive_directory(path: Path) -> list[Path]:
    files = [
        entry
        for entry in path.rglob("*")
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort(key=lambda entry: entry.relative_to(path).as_posix().lower())
    return files
