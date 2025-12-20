"""Textual-based TUI for RhythmSlicer Pro."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Callable, Optional

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Vertical
    from textual.widgets import Static
except Exception as exc:  # pragma: no cover - depends on environment
    raise RuntimeError(
        "Textual is required for the TUI. Install the 'textual' dependency."
    ) from exc

from rhythm_slicer.player_vlc import VlcPlayer


def visualizer_bars(seed_ms: int, width: int, height: int) -> list[int]:
    """Return deterministic bar heights for the visualizer."""
    if width <= 0 or height <= 0:
        return []
    t = seed_ms / 1000.0
    bars: list[int] = []
    for col in range(width):
        base = math.sin(t * 2.0 + col * 0.7)
        mod = math.sin(t * 0.7 + col * 1.3 + (col % 3) * 0.5)
        value = (base + mod) / 2.0
        normalized = (value + 1.0) / 2.0
        level = int(normalized * height)
        bars.append(min(height, max(0, level)))
    return bars


def render_visualizer(bars: list[int], height: int) -> str:
    """Render bar heights into a multi-line ASCII visualizer."""
    if height <= 0 or not bars:
        return ""
    width = len(bars)
    lines: list[str] = []
    for row in range(height):
        threshold = height - row
        line = "".join("#" if bars[col] >= threshold else " " for col in range(width))
        lines.append(line)
    return "\n".join(lines)


def _format_time_ms(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    total_seconds = max(0, value // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def _display_state(state: str) -> str:
    return state.capitalize() if state else "Unknown"


@dataclass
class TuiMessage:
    text: str
    until: float


class RhythmSlicerApp(App):
    """RhythmSlicer Pro Textual application."""

    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("space", "toggle_playback", "Play/Pause"),
        Binding("s", "stop", "Stop"),
        Binding("left", "seek_back", "Seek -5s"),
        Binding("right", "seek_forward", "Seek +5s"),
        Binding("up", "volume_up", "Volume +5"),
        Binding("down", "volume_down", "Volume -5"),
        Binding("n", "next_track", "Next"),
        Binding("p", "previous_track", "Previous"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        *,
        player: VlcPlayer,
        path: str,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.player = player
        self.path = path
        self._filename = Path(path).name
        self._volume = 100
        self._now = now
        self._message: Optional[TuiMessage] = None
        self._header: Optional[Static] = None
        self._visualizer: Optional[Static] = None
        self._status: Optional[Static] = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="header")
            with Container(id="main"):
                yield Static(id="visualizer")
            yield Static(id="status")

    def on_mount(self) -> None:
        self._header = self.query_one("#header", Static)
        self._visualizer = self.query_one("#visualizer", Static)
        self._status = self.query_one("#status", Static)
        if self._visualizer:
            self._visualizer.border_title = "Visualizer"
        self.player.load(self.path)
        self.player.play()
        self.set_interval(0.1, self._on_tick)

    def _set_message(self, text: str, duration: float = 2.0) -> None:
        self._message = TuiMessage(text=text, until=self._now() + duration)

    def _pop_message(self) -> Optional[str]:
        if self._message and self._message.until > self._now():
            return self._message.text
        self._message = None
        return None

    def _render_status(self) -> str:
        state = _display_state(self.player.get_state())
        position = _format_time_ms(self.player.get_position_ms())
        length = _format_time_ms(self.player.get_length_ms())
        timing = f"{position or '--:--'} / {length or '--:--'}"
        hotkeys = "Keys: Space S ←/→ ↑/↓ N/P Q"
        message = self._pop_message()
        base = f"State: {state} | Time: {timing} | Vol: {self._volume} | {hotkeys}"
        return f"{message} | {base}" if message else base

    def _on_tick(self) -> None:
        if self._header:
            self._header.update(f"RhythmSlicer Pro | {self._filename}")
        if self._visualizer:
            size = getattr(self._visualizer, "content_size", None) or self._visualizer.size
            width = max(1, size.width)
            height = max(1, size.height)
            position = self.player.get_position_ms()
            seed_ms = position if position is not None else int(time.time() * 1000)
            bars = visualizer_bars(seed_ms, width, height)
            self._visualizer.update(render_visualizer(bars, height))
        if self._status:
            self._status.update(self._render_status())

    def _try_seek(self, delta_ms: int) -> None:
        seek = getattr(self.player, "seek_ms", None)
        if callable(seek):
            if seek(delta_ms):
                return
        self._set_message("Seek unsupported")

    def action_toggle_playback(self) -> None:
        state = self.player.get_state()
        if state == "playing":
            self.player.pause()
            self._set_message("Paused")
        else:
            self.player.play()
            self._set_message("Playing")

    def action_stop(self) -> None:
        self.player.stop()
        self._set_message("Stopped")

    def action_seek_back(self) -> None:
        self._try_seek(-5000)

    def action_seek_forward(self) -> None:
        self._try_seek(5000)

    def action_volume_up(self) -> None:
        self._volume = min(100, self._volume + 5)
        self.player.set_volume(self._volume)
        self._set_message(f"Volume {self._volume}")

    def action_volume_down(self) -> None:
        self._volume = max(0, self._volume - 5)
        self.player.set_volume(self._volume)
        self._set_message(f"Volume {self._volume}")

    def action_next_track(self) -> None:
        self._set_message("Next track not implemented")

    def action_previous_track(self) -> None:
        self._set_message("Previous track not implemented")

    def action_quit_app(self) -> None:
        self.player.stop()
        self.exit()


def run_tui(path: str, player: VlcPlayer) -> int:
    """Run the TUI and return an exit code."""
    app = RhythmSlicerApp(player=player, path=path)
    app.run()
    return 0
