"""Helpers for the playlist builder screen."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import sys
import threading
import time
import traceback
from typing import Callable
from typing import Iterable, Iterator, Literal, TypeVar

from rhythm_slicer.playlist import SUPPORTED_EXTENSIONS, Track

FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


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

    def is_at_root(self) -> bool:
        return self._parent_path(self._current) == self._current

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


ProgressCallback = Callable[[int, int, int, Path], None]


@dataclass
class _ScanCounters:
    dirs: int = 0
    files: int = 0
    found: int = 0


def collect_audio_files(
    paths: Iterable[Path],
    *,
    allow_hidden_roots: Iterable[Path] | None = None,
    cancel_event: threading.Event | None = None,
    check_every: int = 100,
    sort_entries: bool = False,
    sort_results: bool = False,
    progress: ProgressCallback | None = None,
    progress_every: int = 200,
) -> list[Path]:
    """Collect supported audio files from files or folders (recursive)."""
    found: list[Path] = []
    seen: set[Path] = set()
    allow_hidden_set = (
        {_safe_resolve(path) for path in allow_hidden_roots}
        if allow_hidden_roots
        else set()
    )
    check_every = max(1, check_every)
    progress_every = max(1, progress_every)
    counters = _ScanCounters()
    for path in paths:
        if cancel_event and cancel_event.is_set():
            break
        allow_hidden = _safe_resolve(path) in allow_hidden_set
        for item in _walk_audio_files(
            path,
            allow_hidden=allow_hidden,
            cancel_event=cancel_event,
            check_every=check_every,
            sort_entries=sort_entries,
            counters=counters,
            progress=progress,
            progress_every=progress_every,
        ):
            resolved = _safe_resolve(item)
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(item)
            counters.found += 1
            if progress:
                progress(counters.dirs, counters.files, counters.found, item.parent)
    if sort_results:
        found.sort(key=lambda item: str(item).casefold())
    return found


def build_track_from_path(path: Path) -> Track:
    title = path.name
    return Track(path=path, title=title)


def list_drives() -> list[Path]:
    """Return available drive roots for the current platform."""
    if sys.platform.startswith("win"):
        drives: list[Path] = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            path = Path(f"{letter}:/")
            if path.exists():
                drives.append(path)
        return drives
    roots = [Path("/")]
    candidates = [Path("/Volumes"), Path("/mnt"), Path("/media"), Path("/run/media")]
    for base in candidates:
        if not base.exists() or not base.is_dir():
            continue
        for entry in base.iterdir():
            if entry.is_dir():
                roots.append(entry)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in roots:
        if path in seen:
            continue
        seen.add(path)
        unique.append(path)
    return unique


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


def is_hidden_or_system(path: Path, *, include_parents: bool = False) -> bool:
    """Return True if a path is hidden/system, optionally including parents."""
    if not include_parents:
        return _component_hidden_or_system(path)
    current = path
    while True:
        if _component_hidden_or_system(current):
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def _walk_audio_files(
    path: Path,
    *,
    allow_hidden: bool = False,
    cancel_event: threading.Event | None = None,
    check_every: int = 100,
    sort_entries: bool = False,
    counters: _ScanCounters | None = None,
    progress: ProgressCallback | None = None,
    progress_every: int = 200,
) -> Iterator[Path]:
    if cancel_event and cancel_event.is_set():
        return
    if not allow_hidden and is_hidden_or_system(path):
        return
    check_every = max(1, check_every)
    if path.is_dir():
        files_seen = 0
        dirs_seen = 0
        for root, dirs, files in os.walk(path):
            dirs_seen += 1
            if cancel_event and cancel_event.is_set():
                return
            root_path = Path(root)
            if not allow_hidden and is_hidden_or_system(root_path):
                dirs[:] = []
                continue
            if counters is not None:
                counters.dirs += 1
            if dirs_seen % check_every == 0:
                time.sleep(0)
            if cancel_event and cancel_event.is_set():
                return
            if sort_entries:
                dirs.sort(key=str.casefold)
                files.sort(key=str.casefold)
            if cancel_event and cancel_event.is_set():
                return
            if not allow_hidden:
                dirs[:] = [
                    name for name in dirs if not is_hidden_or_system(root_path / name)
                ]
            for name in files:
                files_seen += 1
                if cancel_event and cancel_event.is_set():
                    return
                if files_seen % check_every == 0:
                    time.sleep(0)
                if cancel_event and cancel_event.is_set():
                    return
                item = root_path / name
                if not allow_hidden and is_hidden_or_system(item):
                    continue
                if counters is not None:
                    counters.files += 1
                if progress and counters is not None:
                    if counters.files % progress_every == 0:
                        progress(counters.dirs, counters.files, counters.found, root_path)
                if _is_supported(item):
                    yield item
            if progress and counters is not None:
                progress(counters.dirs, counters.files, counters.found, root_path)
        return
    if path.is_file() and _is_supported(path):
        if cancel_event and cancel_event.is_set():
            return
        yield path


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _component_hidden_or_system(path: Path) -> bool:
    name = path.name
    if name and name not in {".", ".."} and name.startswith("."):
        return True
    if path.parent == path:
        return False
    if not sys.platform.startswith("win"):
        return False
    attrs = _windows_file_attributes(path)
    if attrs is None:
        return False
    return bool(attrs & (FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM))


def _windows_file_attributes(path: Path) -> int | None:
    try:
        import ctypes
    except Exception:
        return None
    try:
        get_attrs = ctypes.windll.kernel32.GetFileAttributesW  # type: ignore[attr-defined]
    except AttributeError:
        return None
    get_attrs.argtypes = [ctypes.c_wchar_p]
    get_attrs.restype = ctypes.c_uint32
    attrs = int(get_attrs(str(path)))
    if attrs == INVALID_FILE_ATTRIBUTES:
        return None
    return attrs


def run_collect_audio_files(
    paths: list[str],
    allow_hidden_roots: list[str],
    out_q,
) -> None:
    """Process worker entrypoint for recursive audio scan."""
    try:
        path_objs = [Path(path) for path in paths]
        allow_hidden = (
            [Path(path) for path in allow_hidden_roots] if allow_hidden_roots else None
        )
        last_emit = 0.0

        def emit_progress(dirs: int, files: int, found: int, current: Path) -> None:
            nonlocal last_emit
            now = time.monotonic()
            if now - last_emit < 0.2:
                return
            last_emit = now
            out_q.put(
                (
                    "progress",
                    {
                        "dirs": dirs,
                        "files": files,
                        "found": found,
                        "path": str(current),
                    },
                )
            )

        found = collect_audio_files(
            path_objs,
            allow_hidden_roots=allow_hidden,
            sort_results=True,
            progress=emit_progress,
            progress_every=200,
        )
        out_q.put(("ok", [str(path) for path in found]))
    except Exception:
        out_q.put(("error", traceback.format_exc()))
