"""Drive selection prompt for the TUI."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Select, Static


class DrivePrompt(ModalScreen[Optional[Path]]):
    """Modal prompt that lets users pick a drive/root."""

    def __init__(self, drives: Iterable[Path]) -> None:
        super().__init__()
        self._drives = list(drives)
        self._selected: Optional[Path] = self._drives[0] if self._drives else None

    def compose(self) -> ComposeResult:
        options = [(str(path), str(path)) for path in self._drives]
        with Container(id="drive_prompt"):
            yield Static("Select Drive", id="drive_prompt_title")
            yield Select(options, id="drive_prompt_select")
            with Horizontal(id="drive_prompt_buttons"):
                yield Button("OK", id="drive_prompt_ok", disabled=not self._drives)
                yield Button("Cancel", id="drive_prompt_cancel")

    def on_mount(self) -> None:
        select = self.query_one("#drive_prompt_select", Select)
        if self._drives:
            select.value = str(self._drives[0])
        select.focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.value is Select.BLANK:
            self._selected = None
            return
        self._selected = Path(str(event.value))

    def _confirm(self) -> None:
        if self._selected is None:
            return
        self.dismiss(self._selected)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "drive_prompt_ok":
            self._confirm()
            return
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key == "enter":
            self._confirm()
