# Don't Change list:

* [ ] No keybindings changed
* [ ] No widget IDs changed (`#status_time_bar`, etc.)
* [ ] No CSS selector changes
* [ ] No action method names changed (Textual actions)
* [ ] No public API changes (anything imported elsewhere)
* [ ] All tests pass
* [ ] Manual smoke: launch app, play/pause, seek, volume, speed, quit

## Files that use tui.py
    - cli.py
      - run_tui
    - test_cli.py
    - test_help_modal.py
      - RhythmSlicerApp

## Top lines of tui

```python
from __future__ import annotations

from dataclasses import dataclass
import importlib
import pkgutil
import asyncio
import math
import random
from pathlib import Path
import time
from typing import Any, Callable, Iterator, Optional, cast
import logging
from typing_extensions import TypeAlias

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual import events
    from textual.geometry import Region
    from textual.screen import ModalScreen
    from textual.widgets import Button, DataTable, Header, Input, Static
    from textual.widgets.data_table import RowDoesNotExist
    from textual.timer import Timer
    from textual.widget import Widget
    from rich.text import Text
    import textual.widgets as textual_widgets

    TextualPanel = getattr(textual_widgets, "Panel", None)

    class PanelFallback(Container):
        def __init__(
            self,
            *children: Widget,
            title: str | None = None,
            id: str | None = None,
            classes: str | None = None,
            disabled: bool = False,
        ) -> None:
            super().__init__(*children, id=id, classes=classes, disabled=disabled)
            if title:
                self.border_title = title

    Panel = TextualPanel or PanelFallback
except Exception as exc:  # pragma: no cover - depends on environment
    raise RuntimeError(
        "Textual is required for the TUI. Install the 'textual' dependency."
    ) from exc

from rhythm_slicer.config import AppConfig, load_config, save_config
from rhythm_slicer.hackscript import HackFrame, generate as generate_hackscript
from rhythm_slicer.hangwatch import HangWatchdog, dump_threads
from rhythm_slicer.logging_setup import set_console_level
from rhythm_slicer.ui.help_modal import HelpModal
from rhythm_slicer.ui.playlist_builder import PlaylistBuilderScreen
from rhythm_slicer.visualizations.ansi import sanitize_ansi_sgr
from rhythm_slicer.metadata import (
    TrackMeta,
    format_display_title,
    get_cached_track_meta,
    get_track_meta,
)
from rhythm_slicer.player_vlc import VlcPlayer
from rhythm_slicer.playlist import (
    Playlist,
    Track,
    load_from_input,
    SUPPORTED_EXTENSIONS,
)

logger = logging.getLogger(__name__)

TrackSignature: TypeAlias = tuple[
    Optional[str],
    str,
    str,
    str,
    int,
    int,
]
```
