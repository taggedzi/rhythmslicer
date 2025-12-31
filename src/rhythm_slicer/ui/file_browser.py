"""DirectoryTree-based file browser widget."""

from __future__ import annotations

import inspect
from pathlib import Path
import sys
from typing import Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Button, DirectoryTree, Label, ListItem, ListView, Static

from rhythm_slicer.playlist_builder import list_drives
from rhythm_slicer.ui.drive_prompt import DrivePrompt

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

    def __init__(
        self,
        start_path: Path,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ) -> None:
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self._start_path = start_path
        self._root = self._pick_root(start_path)
        self._selected_path: Optional[Path] = None
        self._current_directory = start_path
        self._show_files = _supports_show_files()

    @staticmethod
    def _pick_root(path: Path) -> Path:
        if path.anchor:
            return Path(path.anchor)
        return Path("/")

    @property
    def selected_path(self) -> Optional[Path]:
        return self._selected_path

    @property
    def current_directory(self) -> Path:
        return self._current_directory

    def set_selected_path(self, path: Optional[Path]) -> None:
        self._selected_path = path

    def compose(self) -> ComposeResult:
        with Vertical(id="file_browser_stack"):
            with Horizontal(id="file_browser_header"):
                yield Button("Up", id="file_browser_up")
                yield Button("Drives", id="file_browser_drives")
                current = Static("", id="file_browser_current")
                current.can_focus = False
                yield current
            if self._show_files:
                with Container(id="file_browser_body"):
                    yield DirectoryTree(  # type: ignore[call-arg]
                        self._root, id="file_browser_tree", show_files=True
                    )
            else:
                with Horizontal(id="file_browser_body"):
                    yield DirectoryTree(self._root, id="file_browser_tree")
                    list_view = ListView(id="file_browser_list")
                    list_view.can_focus = False
                    yield list_view

    def on_mount(self) -> None:
        tree = self.query_one("#file_browser_tree", DirectoryTree)
        tree.focus()
        self._update_root_label(tree)
        self._update_current_label()
        if not self._show_files:
            self._refresh_file_list(self._current_directory)

    def _update_root_label(self, tree: DirectoryTree) -> None:
        drive = self._root.drive
        if not drive:
            return
        tree.root.set_label(f"{self._root} [{drive}]")

    def _update_current_label(self) -> None:
        label = self.query_one("#file_browser_current", Static)
        label.update(f"Current: {self._current_directory}")

    def _set_current_directory(
        self, directory: Path, *, selected_path: Optional[Path] = None
    ) -> None:
        self._current_directory = directory
        if selected_path is not None:
            self._selected_path = selected_path
        self._update_current_label()

    def _refresh_file_list(self, directory: Path) -> None:
        list_view = self.query_one("#file_browser_list", ListView)
        list_view.clear()
        try:
            entries = sorted(
                (entry for entry in directory.iterdir() if entry.is_file()),
                key=lambda entry: entry.name.casefold(),
            )
        except OSError:
            entries = []
        list_view.can_focus = bool(entries)
        if not entries and list_view.has_focus:
            tree = self.query_one("#file_browser_tree", DirectoryTree)
            tree.focus()
        for entry in entries:
            list_view.append(FileBrowserItem(entry))

    @staticmethod
    def _normalize_drive_root(path: Path) -> Path:
        if sys.platform.startswith("win") and path.anchor:
            return Path(path.anchor)
        return path

    async def _prompt_for_drive(self) -> Optional[Path]:
        drives = list_drives()
        if not drives:
            return None
        return await self.app.push_screen_wait(DrivePrompt(drives))

    async def _handle_drive_selection(self) -> None:
        selected = await self._prompt_for_drive()
        if not selected:
            return
        new_root = self._normalize_drive_root(selected)
        self._root = new_root
        tree = self.query_one("#file_browser_tree", DirectoryTree)
        tree.path = new_root
        self._update_root_label(tree)
        self._set_current_directory(new_root, selected_path=new_root)
        if not self._show_files:
            self._refresh_file_list(new_root)
        tree.focus()

    def _run_drive_selection(self) -> None:
        self.app.run_worker(
            self._handle_drive_selection(),
            name="file_browser_drive_selection",
            exclusive=True,
        )

    def _handle_up_action(self) -> None:
        if self._current_directory == self._root:
            self._run_drive_selection()
            return
        parent = self._current_directory.parent
        self._set_current_directory(parent, selected_path=parent)
        if not self._show_files:
            self._refresh_file_list(parent)

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._set_current_directory(event.path, selected_path=event.path)
        if not self._show_files:
            self._refresh_file_list(event.path)

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self._set_current_directory(event.path.parent, selected_path=event.path)

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        item = event.item
        if isinstance(item, FileBrowserItem):
            self.set_selected_path(item.path)
        else:
            self.set_selected_path(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "file_browser_up":
            self._handle_up_action()
            return
        if event.button.id == "file_browser_drives":
            self._run_drive_selection()

    def on_key(self, event: events.Key) -> None:
        if event.key not in {"backspace", "left"}:
            return
        tree = self.query_one("#file_browser_tree", DirectoryTree)
        if not tree.has_focus:
            return
        event.stop()
        self._handle_up_action()
