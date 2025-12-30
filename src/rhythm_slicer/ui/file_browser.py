"""DirectoryTree-based file browser widget."""

from __future__ import annotations

from pathlib import Path
import inspect
from typing import Optional

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widget import Widget
from textual.widgets import DirectoryTree, Label, ListItem, ListView


def _supports_show_files() -> bool:
    try:
        return "show_files" in inspect.signature(DirectoryTree).parameters
    except (TypeError, ValueError):
        return False


class FileBrowserItem(ListItem):
    """List item that tracks a file path."""

    def __init__(self, path: Path) -> None:
        super().__init__(Label(path.name))
        self.path = path


class FileBrowserWidget(Widget):
    """Single-selection file browser backed by a DirectoryTree."""

    def __init__(self, start_path: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._start_path = start_path
        self._selected_path: Optional[Path] = None
        self._current_directory = start_path
        self._show_files = _supports_show_files()

    @property
    def selected_path(self) -> Optional[Path]:
        return self._selected_path

    @property
    def current_directory(self) -> Path:
        return self._current_directory

    def set_selected_path(self, path: Optional[Path]) -> None:
        self._selected_path = path

    def compose(self) -> ComposeResult:
        if self._show_files:
            yield DirectoryTree(
                self._start_path, id="file_browser_tree", show_files=True
            )
            return
        with Horizontal(id="file_browser_body"):
            yield DirectoryTree(self._start_path, id="file_browser_tree")
            yield ListView(id="file_browser_list")

    def on_mount(self) -> None:
        tree = self.query_one("#file_browser_tree", DirectoryTree)
        tree.focus()
        if not self._show_files:
            self._refresh_file_list(self._start_path)

    def _refresh_file_list(self, directory: Path) -> None:
        self._current_directory = directory
        list_view = self.query_one("#file_browser_list", ListView)
        list_view.clear()
        try:
            entries = sorted(
                (entry for entry in directory.iterdir() if entry.is_file()),
                key=lambda entry: entry.name.casefold(),
            )
        except OSError:
            entries = []
        for entry in entries:
            list_view.append(FileBrowserItem(entry))

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._current_directory = event.path
        self.set_selected_path(event.path)
        if not self._show_files:
            self._refresh_file_list(event.path)

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self._current_directory = event.path.parent
        self.set_selected_path(event.path)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if isinstance(item, FileBrowserItem):
            self.set_selected_path(item.path)
        else:
            self.set_selected_path(None)
