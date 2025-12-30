"""Help modal for RhythmSlicer."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from rich.text import Text
from textual.app import ComposeResult
from textual import events
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static


_SECTION_ACTIONS: dict[str, list[str]] = {
    "Playback": [
        "toggle_playback",
        "stop",
        "seek_back",
        "seek_forward",
        "next_track",
        "previous_track",
    ],
    "Playlist": [
        "move_up",
        "move_down",
        "play_selected",
        "remove_selected",
        "save_playlist",
        "playlist_builder",
    ],
    "Visualizer": [
        "select_visualization",
    ],
    "General": [
        "volume_up",
        "volume_down",
        "cycle_repeat",
        "toggle_shuffle",
        "show_help",
        "quit_app",
    ],
    "Troubleshooting": [
        "dump_threads",
    ],
}

_ACTION_OVERRIDES: dict[str, str] = {
    "select_visualization": "Change visualization",
    "show_help": "Open help",
}

_BUILDER_HELP: list[tuple[str, str]] = [
    (
        "Files pane",
        "Up/Down Move | Enter/Right Open | Left Up | Space Select | "
        "F5 Add | Ins Filter | Tab Switch | Esc Clear/Back",
    ),
    (
        "Playlist pane",
        "Up/Down Move | Space Select | d Delete | u/j Move Up/Down | "
        "s Save | S Save As | l Load | Tab Switch | Esc Clear/Back",
    ),
]


def _format_key(key: str) -> str:
    key_map = {
        "left": "←",
        "right": "→",
        "up": "↑",
        "down": "↓",
        "space": "Space",
        "enter": "Enter",
    }
    if key in key_map:
        return key_map[key]
    parts = key.split("+")
    formatted: list[str] = []
    for part in parts:
        if len(part) == 1:
            formatted.append(part.upper())
        else:
            formatted.append(part.capitalize())
    return "+".join(formatted)


def build_help_text(bindings: Iterable[Binding]) -> Text:
    by_action: dict[str, list[str]] = defaultdict(list)
    by_desc: dict[str, str] = {}
    for binding in bindings:
        by_action[binding.action].append(binding.key)
        if binding.description:
            by_desc[binding.action] = binding.description

    content = Text()
    first_section = True
    for section, actions in _SECTION_ACTIONS.items():
        if not first_section:
            content.append("\n")
        first_section = False
        content.append(f"{section}\n", style="bold #5fc9d6")
        for action in actions:
            keys = by_action.get(action)
            if not keys:
                continue
            key_text = ", ".join(_format_key(key) for key in keys)
            label = _ACTION_OVERRIDES.get(action, by_desc.get(action, action))
            content.append(f"{key_text} — {label}\n")

        if section == "Troubleshooting":
            content.append(
                "Logs — %LOCALAPPDATA%/RhythmSlicer/logs or ~/.rhythm_slicer/logs\n"
            )

    if _BUILDER_HELP:
        content.append("\n")
        content.append("Playlist Builder\n", style="bold #5fc9d6")
        for label, description in _BUILDER_HELP:
            content.append(f"{label} — {description}\n")

    return content


class HelpModal(ModalScreen[None]):
    """Help modal listing keybinds and usage."""

    def __init__(self, bindings: Iterable[Binding]) -> None:
        super().__init__()
        self._help_bindings = list(bindings)

    def compose(self) -> ComposeResult:
        content = build_help_text(self._help_bindings)
        with Vertical(id="help_modal"):
            yield Static("RhythmSlicer Help", id="help_title")
            with VerticalScroll(id="help_scroll"):
                yield Static(content, id="help_content")
            with Horizontal(id="help_footer"):
                yield Static("Esc/q — Close", id="help_hint")
                yield Button("Close", id="help_close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "help_close":
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key in {"escape", "q"}:
            self.dismiss(None)
