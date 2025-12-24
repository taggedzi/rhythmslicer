"""Helpers for the playlist builder screen."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterable, Iterator, Literal, TypeVar

from rhythm_slicer.metadata import format_display_title, get_track_meta
from rhythm_slicer.playlist import SUPPORTED_EXTENSIONS, Track


@dataclass(frozen=True)
class BrowserEntry:
    """Filesystem entry model for the browser pane."""

    name: str
    path: Path
    is_dir: bool
    is_parent: bool = False


class FileBrowserModel:
    """Simple filesystem browser model with selection state."""

    def __init__(self, start_path: Path) -> None:
        self._current = self._normalize_start(start_path)
        self._selection: set[Path] = set()

    @property
    def current_path(self) -> Path:
        return self._current

    def list_entries(self) -> list[BrowserEntry]:
        entries: list[BrowserEntry] = []
        parent = self._parent_path(self._current)
        entries.append(
            BrowserEntry(name="..", path=parent, is_dir=True, is_parent=True)
        )
        try:
            children = list(self._current.iterdir())
        except OSError:
            return entries
        dirs = sorted(
            (path for path in children if path.is_dir()),
            key=lambda path: path.name.casefold(),
        )
        files = sorted(
            (path for path in children if path.is_file()),
            key=lambda path: path.name.casefold(),
        )
        entries.extend(
            BrowserEntry(name=path.name, path=path, is_dir=True) for path in dirs
        )
        entries.extend(
            BrowserEntry(name=path.name, path=path, is_dir=False) for path in files
        )
        return entries

    def change_directory(self, path: Path) -> bool:
        target = path
        if not target.exists() or not target.is_dir():
            return False
        self._current = target
        self.clear_selection()
        return True

    def go_up(self) -> bool:
        parent = self._parent_path(self._current)
        return self.change_directory(parent)

    def toggle_selection(self, entry: BrowserEntry) -> bool:
        if entry.is_parent:
            return False
        if entry.path in self._selection:
            self._selection.remove(entry.path)
            return False
        self._selection.add(entry.path)
        return True

    def clear_selection(self) -> None:
        self._selection.clear()

    def selected_paths(self) -> list[Path]:
        return sorted(self._selection, key=lambda path: path.name.casefold())

    def is_selected(self, path: Path) -> bool:
        return path in self._selection

    @staticmethod
    def _normalize_start(path: Path) -> Path:
        if path.exists() and path.is_dir():
            return path
        if path.exists() and path.is_file():
            return path.parent
        return Path.cwd()

    @staticmethod
    def _parent_path(path: Path) -> Path:
        if path.parent == path:
            return path
        return path.parent


def collect_audio_files(paths: Iterable[Path]) -> list[Path]:
    """Collect supported audio files from files or folders (recursive)."""
    found: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        for item in _walk_audio_files(path):
            resolved = _safe_resolve(item)
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(item)
    return found


def build_track_from_path(path: Path) -> Track:
    meta = get_track_meta(path)
    title = format_display_title(path, meta)
    return Track(path=path, title=title)


T = TypeVar("T")


def reorder_items(
    items: list[T],
    selected_indices: Iterable[int],
    direction: Literal["up", "down"],
) -> tuple[list[T], list[int]]:
    """Move selected indices up/down by one, preserving relative order."""
    count = len(items)
    selected = sorted({idx for idx in selected_indices if 0 <= idx < count})
    if not selected:
        return list(items), []
    reordered = list(items)
    selected_set = set(selected)
    if direction == "up":
        for idx in selected:
            if idx == 0 or (idx - 1) in selected_set:
                continue
            reordered[idx - 1], reordered[idx] = reordered[idx], reordered[idx - 1]
            selected_set.remove(idx)
            selected_set.add(idx - 1)
    else:
        for idx in sorted(selected, reverse=True):
            if idx >= count - 1 or (idx + 1) in selected_set:
                continue
            reordered[idx + 1], reordered[idx] = reordered[idx], reordered[idx + 1]
            selected_set.remove(idx)
            selected_set.add(idx + 1)
    return reordered, sorted(selected_set)


def _walk_audio_files(path: Path) -> Iterator[Path]:
    if path.is_dir():
        for root, dirs, files in os.walk(path):
            dirs.sort(key=str.casefold)
            files.sort(key=str.casefold)
            for name in files:
                item = Path(root) / name
                if _is_supported(item):
                    yield item
        return
    if path.is_file() and _is_supported(path):
        yield path


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()
