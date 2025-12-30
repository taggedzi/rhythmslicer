"""Playlist file picker screen for the TUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Optional, cast

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DirectoryTree,
    Label,
    ListItem,
    ListView,
    Static,
)

from rhythm_slicer.playlist import M3U_EXTENSIONS

PLAYLIST_EXTENSIONS = frozenset(M3U_EXTENSIONS)


def filter_playlist_filenames(
    names: Iterable[str], *, extensions: Iterable[str] | None = None
) -> list[str]:
    """Return filenames that match supported playlist extensions."""
    ext_set = {ext.lower() for ext in (extensions or PLAYLIST_EXTENSIONS)}
    return [name for name in names if Path(name).suffix.lower() in ext_set]


def playlist_files_in_directory(
    directory: Path, *, extensions: Iterable[str] | None = None
) -> list[Path]:
    """Return playlist files in a directory sorted by name."""
    ext_set = {ext.lower() for ext in (extensions or PLAYLIST_EXTENSIONS)}
    try:
        entries = [
            entry
            for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.lower() in ext_set
        ]
    except FileNotFoundError:
        entries = []
    entries.sort(key=lambda entry: entry.name.lower())
    return entries


def pick_start_directory(last_playlist_path: Optional[Path], cwd: Path) -> Path:
    """Pick a start directory for the playlist file picker."""
    if last_playlist_path:
        candidate = (
            last_playlist_path
            if last_playlist_path.is_dir()
            else last_playlist_path.parent
        )
        if candidate.exists() and candidate.is_dir():
            return candidate
    if cwd.exists() and cwd.is_dir():
        return cwd
    return Path.cwd()


class PlaylistFileItem(ListItem):
    """List item that tracks the playlist file path."""

    def __init__(self, path: Path) -> None:
        super().__init__(Label(path.name))
        self.path = path


class PlaylistFilePicker(ModalScreen[Optional[Path]]):
    """Modal screen that lets users pick a playlist file."""

    def __init__(self, start_directory: Path) -> None:
        super().__init__()
        self._start_directory = start_directory
        self._current_directory = start_directory
        self._selected_path: Optional[Path] = None

    def compose(self) -> ComposeResult:
        with Container(id="playlist_file_picker"):
            yield Static("Load Playlist", id="playlist_file_title")
            with Horizontal(id="playlist_file_body"):
                yield DirectoryTree(self._start_directory, id="playlist_file_tree")
                yield ListView(id="playlist_file_list")
            yield Static("Selected: No file selected", id="playlist_file_selected")
            with Horizontal(id="playlist_file_buttons"):
                yield Button("OK", id="playlist_file_ok", disabled=True)
                yield Button("Cancel", id="playlist_file_cancel")

    def on_mount(self) -> None:
        self._refresh_file_list(self._start_directory)
        list_view = self.query_one("#playlist_file_list", ListView)
        if list_view.children:
            list_view.focus()
        else:
            self.query_one("#playlist_file_tree", DirectoryTree).focus()

    def _refresh_file_list(self, directory: Path) -> None:
        self._current_directory = directory
        list_view = self.query_one("#playlist_file_list", ListView)
        list_view.clear()
        for entry in playlist_files_in_directory(directory):
            list_view.append(PlaylistFileItem(entry))
        self.set_selected_path(None)

    def set_selected_path(self, path: Optional[Path]) -> None:
        self._selected_path = path
        label = self.query_one("#playlist_file_selected", Static)
        ok_button = self.query_one("#playlist_file_ok", Button)
        if path:
            label.update(f"Selected: {path}")
            ok_button.disabled = False
        else:
            label.update("Selected: No file selected")
            ok_button.disabled = True

    def confirm_selection(self) -> None:
        if self._selected_path:
            self.dismiss(self._selected_path)

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._refresh_file_list(event.path)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if isinstance(item, PlaylistFileItem):
            self.set_selected_path(item.path)
        else:
            self.set_selected_path(None)

    def on_click(self, event: events.Click) -> None:
        event_any = cast(Any, event)
        widget = getattr(event_any, "widget", None)
        if isinstance(widget, PlaylistFileItem):
            self.set_selected_path(widget.path)
            clicks = getattr(event_any, "clicks", 1)
            if clicks > 1:
                self.confirm_selection()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "playlist_file_ok":
            self.confirm_selection()
        else:
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key == "enter":
            self.confirm_selection()
