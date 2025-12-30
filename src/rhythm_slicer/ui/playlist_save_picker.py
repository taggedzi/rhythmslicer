"""Playlist save picker modal for the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal, Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Static

from rhythm_slicer.playlist import M3U_EXTENSIONS


@dataclass(frozen=True)
class SaveResult:
    """Result payload from PlaylistSavePicker."""

    target_path: Path
    save_absolute: bool


def save_mode_from_flag(save_absolute: bool) -> Literal["absolute", "auto"]:
    return "absolute" if save_absolute else "auto"


def _normalize_extension(extension: str) -> str:
    if not extension:
        return ""
    return extension if extension.startswith(".") else f".{extension}"


def _normalize_filename(filename: str) -> str:
    cleaned = filename.strip()
    if not cleaned:
        return ""
    return Path(cleaned).name


def _append_default_extension(
    filename: str, default_extension: str, allowed_extensions: Iterable[str]
) -> str:
    if not filename:
        return filename
    suffix = Path(filename).suffix
    if suffix:
        return filename
    extension = _normalize_extension(default_extension)
    allowed = {ext.lower() for ext in allowed_extensions if ext}
    if allowed and extension.lower() not in allowed:
        if ".m3u8" in allowed:
            extension = ".m3u8"
        else:
            extension = sorted(allowed)[0]
    return f"{filename}{extension}" if extension else filename


def compute_destination_path(
    directory: Path,
    filename: str,
    *,
    default_extension: str = ".m3u8",
    allowed_extensions: Iterable[str] = M3U_EXTENSIONS,
) -> Path:
    normalized = _normalize_filename(filename)
    if not normalized:
        return directory
    final_name = _append_default_extension(
        normalized, default_extension, allowed_extensions
    )
    return directory / final_name


def build_save_result(
    directory: Path,
    filename: str,
    *,
    save_absolute: bool,
    default_extension: str = ".m3u8",
    allowed_extensions: Iterable[str] = M3U_EXTENSIONS,
) -> SaveResult:
    dest = compute_destination_path(
        directory,
        filename,
        default_extension=default_extension,
        allowed_extensions=allowed_extensions,
    )
    return SaveResult(target_path=dest, save_absolute=save_absolute)


class PlaylistSavePicker(ModalScreen[Optional[SaveResult]]):
    """Directory + filename save picker for playlists."""

    def __init__(
        self,
        start_directory: Path,
        default_filename: str,
        *,
        save_absolute_default: bool = False,
        default_extension: str = ".m3u8",
        allowed_extensions: Iterable[str] = M3U_EXTENSIONS,
    ) -> None:
        super().__init__()
        self._start_directory = start_directory
        self._default_filename = default_filename
        self._default_extension = default_extension
        self._allowed_extensions = tuple(allowed_extensions)
        self._selected_directory = start_directory
        self._save_absolute = save_absolute_default

    def compose(self) -> ComposeResult:
        with Container(id="playlist_save_picker"):
            yield Static("Save Playlist", id="save_picker_title")
            with Horizontal(id="save_picker_body"):
                yield DirectoryTree(self._start_directory, id="save_picker_tree")
                with Vertical(id="save_picker_details"):
                    yield Static("Filename", id="save_picker_filename_label")
                    yield Input(
                        value=self._default_filename,
                        id="save_picker_filename",
                    )
                    yield Static("", id="save_picker_destination")
                    label = (
                        "Save absolute paths: On"
                        if self._save_absolute
                        else "Save absolute paths: Off"
                    )
                    yield Button(label, id="save_picker_absolute")
                    with Horizontal(id="save_picker_buttons"):
                        yield Button("Save", id="save_picker_save")
                        yield Button("Cancel", id="save_picker_cancel")

    def on_mount(self) -> None:
        self._refresh_destination()
        self.query_one("#save_picker_filename", Input).focus()

    def _toggle_absolute(self) -> None:
        self._save_absolute = not self._save_absolute
        label = (
            "Save absolute paths: On"
            if self._save_absolute
            else "Save absolute paths: Off"
        )
        self.query_one("#save_picker_absolute", Button).label = label

    def _current_filename(self) -> str:
        return self.query_one("#save_picker_filename", Input).value

    def _destination_path(self) -> Path | None:
        filename = _normalize_filename(self._current_filename())
        if not filename:
            return None
        return compute_destination_path(
            self._selected_directory,
            filename,
            default_extension=self._default_extension,
            allowed_extensions=self._allowed_extensions,
        )

    def _refresh_destination(self) -> None:
        dest = self._destination_path()
        dest_label = self.query_one("#save_picker_destination", Static)
        if dest is None:
            dest_label.update(f"Destination: {self._selected_directory}")
            self.query_one("#save_picker_save", Button).disabled = True
            return
        dest_label.update(f"Destination: {dest}")
        self.query_one("#save_picker_save", Button).disabled = False

    def _confirm(self) -> None:
        dest = self._destination_path()
        if dest is None:
            return
        self.dismiss(
            build_save_result(
                self._selected_directory,
                self._current_filename(),
                save_absolute=self._save_absolute,
                default_extension=self._default_extension,
                allowed_extensions=self._allowed_extensions,
            )
        )

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self._selected_directory = event.path
        self._refresh_destination()

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self._selected_directory = event.path.parent
        filename_input = self.query_one("#save_picker_filename", Input)
        if not filename_input.value.strip():
            filename_input.value = event.path.name
        self._refresh_destination()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "save_picker_filename":
            self._refresh_destination()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "save_picker_absolute":
            self._toggle_absolute()
            return
        if button_id == "save_picker_save":
            self._confirm()
            return
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key == "enter":
            focused = self.app.focused
            if isinstance(focused, Input) or focused is None:
                self._confirm()
