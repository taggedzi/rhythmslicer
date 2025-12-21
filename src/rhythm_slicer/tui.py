"""Textual-based TUI for RhythmSlicer Pro."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import pkgutil
import asyncio
import math
import random
from pathlib import Path
import time
from typing import Callable, Iterator, Optional
import logging

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual import events
    from textual.screen import ModalScreen
    from textual.widgets import Button, Input, Static
    from rich.text import Text
except Exception as exc:  # pragma: no cover - depends on environment
    raise RuntimeError(
        "Textual is required for the TUI. Install the 'textual' dependency."
    ) from exc

from rhythm_slicer.config import AppConfig, load_config, save_config
from rhythm_slicer.hackscript import HackFrame, generate as generate_hackscript
from rhythm_slicer.hangwatch import HangWatchdog, dump_threads
from rhythm_slicer.logging_setup import set_console_level
from rhythm_slicer.ui.help_modal import HelpModal
from rhythm_slicer.visualizations.ansi import sanitize_ansi_sgr
from rhythm_slicer.metadata import format_display_title, get_track_meta
from rhythm_slicer.player_vlc import VlcPlayer
from rhythm_slicer.playlist import Playlist, Track, load_from_input, SUPPORTED_EXTENSIONS

logger = logging.getLogger(__name__)


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


def ratio_from_click(x: int, width: int) -> float:
    """Map a click x position to a 0..1 ratio."""
    if width <= 1:
        return 0.0
    clamped = max(0, min(x, width - 1))
    return clamped / float(width - 1)


def target_ms_from_ratio(length_ms: int, ratio: float) -> int:
    """Return a target time in ms for a ratio of track length."""
    return int(max(0.0, min(1.0, ratio)) * max(0, length_ms))


def build_play_order(
    count: int,
    current_index: int,
    shuffle: bool,
    rng: random.Random,
) -> tuple[list[int], int]:
    """Build a play order and return the order plus the current position."""
    if count <= 0:
        return [], -1
    order = list(range(count))
    if shuffle and count > 1:
        rng.shuffle(order)
    try:
        position = order.index(current_index)
    except ValueError:
        position = 0
    return order, position


class FramePlayer:
    """Non-blocking HackScript frame player for the visualizer."""

    def __init__(self, app: "RhythmSlicerApp") -> None:
        self._app = app
        self._frames: Optional[Iterator[HackFrame]] = None
        self._timer = None

    def start(self, frames: Iterator[HackFrame]) -> None:
        self.stop()
        self._frames = frames
        self._advance()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._frames = None

    @property
    def is_running(self) -> bool:
        return self._frames is not None

    def _advance(self) -> None:
        if self._frames is None:
            return
        try:
            frame = next(self._frames)
        except Exception as exc:
            logger.exception("Visualizer frame error")
            self._app._set_message(f"Visualizer error: {exc}", level="error")
            self.stop()
            return
        except StopIteration:
            self.stop()
            return
        self._app._show_frame(frame)
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.stop()
            return
        delay = max(0.01, frame.hold_ms / 1000.0)
        self._timer = self._app.set_timer(delay, self._advance)


class VisualizerHud(Static):
    """Compact HUD for the visualizer pane."""


@dataclass
class StatusMessage:
    text: str
    level: str
    until: Optional[float]


class StatusController:
    """Status bar state and rendering."""

    def __init__(self, now: Callable[[], float]) -> None:
        self._now = now
        self._message: Optional[StatusMessage] = None
        self._context: Optional[str] = None

    def show_message(
        self,
        text: str,
        *,
        level: str = "info",
        timeout: Optional[float] = None,
    ) -> None:
        if timeout is None:
            if level == "warn":
                timeout = 6.0
            elif level == "error":
                timeout = 0.0
            else:
                timeout = 3.0
        until = None if timeout == 0 else self._now() + max(0.0, timeout)
        self._message = StatusMessage(text=text, level=level, until=until)

    def clear_message(self) -> None:
        self._message = None

    def set_context(self, name: str) -> None:
        self._context = name

    def render_line(self, width: int, *, focused: object | None = None) -> Text:
        message = self._current_message()
        if message:
            line = _truncate_line(message.text, width)
            style = None
            if message.level == "warn":
                style = "#ffcc66"
            elif message.level == "error":
                style = "#ff5f52"
            return Text(line, style=style) if style else Text(line)
        hint = self._render_hint(focused)
        return Text(_truncate_line(hint, width))

    def _current_message(self) -> Optional[StatusMessage]:
        if not self._message:
            return None
        if self._message.until is None:
            return self._message
        if self._message.until > self._now():
            return self._message
        self._message = None
        return None

    def _render_hint(self, focused: object | None) -> str:
        context = self._context or self._context_from_focus(focused)
        if context == "playlist":
            return "Enter: play  Del: remove  ↑↓: navigate  ?: help"
        if context == "visualizer":
            return "V: change viz  R: restart viz  ?: help"
        if context == "transport":
            return "Space: play/pause  ←/→: seek  ?: help"
        return "Space: play/pause  Enter: play  ?: help"

    def _context_from_focus(self, focused: object | None) -> str:
        if focused is None:
            return "general"
        if isinstance(focused, str):
            focus_id = focused
            if focus_id in {"playlist_list", "playlist_pane"}:
                return "playlist"
            if focus_id in {"visualizer", "visualizer_hud", "visuals_pane", "visuals_stack"}:
                return "visualizer"
            if focus_id in {"transport_row", "key_prev", "key_playpause", "key_stop", "key_next"}:
                return "transport"
            return "general"
        if self._focus_has_id(
            focused, {"playlist_list", "playlist_pane"}
        ):
            return "playlist"
        if self._focus_has_id(
            focused,
            {"visualizer", "visualizer_hud", "visuals_pane", "visuals_stack"},
        ):
            return "visualizer"
        if self._focus_has_id(
            focused,
            {"transport_row", "key_prev", "key_playpause", "key_stop", "key_next"},
        ):
            return "transport"
        return "general"

    def _focus_has_id(self, widget: object, ids: set[str]) -> bool:
        current = widget
        while current is not None:
            if getattr(current, "id", None) in ids:
                return True
            current = getattr(current, "parent", None)
        return False


class StatusBar(Static):
    """Status bar widget."""

    def __init__(self, controller: StatusController, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._controller = controller

    def render(self) -> Text:
        width = max(1, self.size.width)
        focused = getattr(self.app, "focused", None)
        return self._controller.render_line(width, focused=focused)


class RhythmSlicerApp(App):
    """RhythmSlicer Pro Textual application."""

    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("space", "toggle_playback", "Play/Pause"),
        Binding("s", "stop", "Stop"),
        Binding("left", "seek_back", "Seek -5s"),
        Binding("right", "seek_forward", "Seek +5s"),
        Binding("up", "move_up", "Select Up"),
        Binding("down", "move_down", "Select Down"),
        Binding("n", "next_track", "Next"),
        Binding("p", "previous_track", "Previous"),
        Binding("enter", "play_selected", "Play Selected"),
        Binding("d", "remove_selected", "Remove Selected"),
        Binding("+", "volume_up", "Volume +5"),
        Binding("-", "volume_down", "Volume -5"),
        Binding("r", "cycle_repeat", "Repeat Mode"),
        Binding("h", "toggle_shuffle", "Shuffle"),
        Binding("v", "select_visualization", "Visualization"),
        Binding("ctrl+s", "save_playlist", "Save Playlist"),
        Binding("ctrl+o", "open", "Open"),
        Binding("ctrl+shift+d", "dump_threads", "Dump Threads"),
        Binding("?", "show_help", "Help"),
        Binding("f1", "show_help", "Help"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        *,
        player: VlcPlayer,
        path: str,
        playlist: Optional[Playlist] = None,
        viz_name: Optional[str] = None,
        now: Callable[[], float] = time.monotonic,
        rng: Optional[random.Random] = None,
    ) -> None:
        super().__init__()
        self.player = player
        self.path = path
        self._explicit_path = bool(path)
        self.playlist = playlist
        self._filename = Path(path).name if path else "RhythmSlicer"
        config = load_config()
        self._config = config
        self._volume = config.volume
        self._now = now
        self._scroll_offset = 0
        self._last_click_time = 0.0
        self._last_click_index: Optional[int] = None
        self._scrub_active = False
        self._repeat_mode = config.repeat_mode
        self._shuffle = config.shuffle
        self._viz_name = viz_name or config.viz_name
        self._ansi_colors = config.ansi_colors
        self._play_order: list[int] = []
        self._play_order_pos = -1
        self._rng = rng or random.Random()
        self._last_playlist_path: Optional[Path] = None
        self._last_open_path: Optional[Path] = (
            Path(config.last_open_path)
            if config.last_open_path
            else None
        )
        self._open_recursive = config.open_recursive
        self._status_controller = StatusController(self._now)
        self._playing_index: Optional[int] = None
        self._header: Optional[Static] = None
        self._visualizer: Optional[Static] = None
        self._visualizer_hud: Optional[Static] = None
        self._playlist_list: Optional[Static] = None
        self._progress: Optional[Static] = None
        self._status: Optional[StatusBar] = None
        self._progress_tick = 0
        self._frame_player = FramePlayer(self)
        self._current_track_path: Optional[Path] = None
        self._viewport_width = 1
        self._viewport_height = 1
        self._last_visualizer_text: Optional[str] = None
        self._viz_prefs: dict[str, object] = {}
        self._viz_restart_timer: Optional[object] = None
        self._visualizer_ready = False
        self._visualizer_init_attempts = 0
        self._last_ui_tick = self._now()
        self._hang_watchdog: Optional[HangWatchdog] = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="header")
            with Container(id="main"):
                with Container(id="playlist_pane"):
                    with Vertical():
                        yield Static(id="playlist_list", markup=True)
                        with Horizontal(id="playlist_footer"):
                            yield Static(id="playlist_footer_track")
                            yield Button("R:OFF", id="repeat_toggle")
                            yield Button("S:OFF", id="shuffle_toggle")
                        yield Horizontal(
                            Button(Text("[<<]"), id="key_prev", classes="transport_key"),
                            Button(Text("[ PLAY ] "), id="key_playpause", classes="transport_key"),
                            Button(Text("[ STOP ]"), id="key_stop", classes="transport_key"),
                            Button(Text("[>>]"), id="key_next", classes="transport_key"),
                            id="transport_row",
                        )
                with Container(id="visuals_pane"):
                    with Vertical(id="visuals_stack"):
                        yield Static(id="visualizer")
                        yield VisualizerHud(id="visualizer_hud")
            yield Static(id="progress")
            yield StatusBar(self._status_controller, id="status")

    async def on_mount(self) -> None:
        self._header = self.query_one("#header", Static)
        self._visualizer = self.query_one("#visualizer", Static)
        self._visualizer_hud = self.query_one("#visualizer_hud", Static)
        self._playlist_list = self.query_one("#playlist_list", Static)
        self._playlist_list.can_focus = True
        playlist_pane = self.query_one("#playlist_pane", Container)
        playlist_pane.border_title = "Playlist"
        self._progress = self.query_one("#progress", Static)
        self._status = self.query_one("#status", StatusBar)
        if self._visualizer:
            self._visualizer.border_title = "Visualizer"
        self._update_visualizer_hud()
        self._update_visualizer_viewport()
        self._install_asyncio_exception_handler()
        self._start_hang_watchdog()
        self.player.set_volume(self._volume)
        if self.playlist is None:
            if not self._explicit_path and self._last_open_path:
                if self._last_open_path.exists():
                    self.playlist = load_from_input(self._last_open_path)
                    self._filename = self._last_open_path.name
            if self.playlist is None and self._explicit_path:
                self.playlist = load_from_input(Path(self.path))
            if self.playlist is None:
                self.playlist = Playlist([])
        await self.set_playlist(self.playlist, preserve_path=None)
        if self.playlist and not self.playlist.is_empty():
            if not self._play_current_track():
                self._skip_failed_track()
        else:
            self._set_message("No tracks loaded")
        if self._playlist_list:
            self.set_focus(self._playlist_list)
        self._update_transport_row()
        self.set_interval(0.1, self._on_tick)
        self.set_interval(0.5, self._update_ui_tick)
        self.set_interval(10.0, self._log_heartbeat)
        self.call_later(self._finalize_visualizer_layout)
        logger.info("TUI mounted")

    def _install_asyncio_exception_handler(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        def handler(_loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exc = context.get("exception")
            if exc:
                logger.exception("Asyncio exception", exc_info=exc)
            else:
                logger.error("Asyncio error: %s", context.get("message"))

        loop.set_exception_handler(handler)

    def _finalize_visualizer_layout(self) -> None:
        if self._visualizer_ready:
            return
        self._update_visualizer_viewport()
        if self._viewport_width <= 2 or self._viewport_height <= 1:
            self._visualizer_init_attempts += 1
            if self._visualizer_init_attempts < 10:
                self.set_timer(0.05, self._finalize_visualizer_layout)
            return
        self._update_visualizer_hud()
        if self._current_track_path:
            self._restart_hackscript_from_player()
        elif self._visualizer and not self._frame_player.is_running:
            self._visualizer.update(self._render_visualizer())
        self._visualizer_ready = True
        logger.info(
            "Visualizer layout ready (%sx%s)", self._viewport_width, self._viewport_height
        )

    def _start_hang_watchdog(self) -> None:
        if self._hang_watchdog:
            return
        self._hang_watchdog = HangWatchdog(
            lambda: self._last_ui_tick,
            threshold_seconds=15.0,
            repeat_seconds=30.0,
        )
        self._hang_watchdog.start()

    def _update_ui_tick(self) -> None:
        self._last_ui_tick = self._now()

    def _log_heartbeat(self) -> None:
        state = self.player.get_state()
        title = None
        track_index = None
        if self.playlist and not self.playlist.is_empty():
            track = self.playlist.current()
            if track:
                title = track.title
                track_index = self.playlist.index
        position = self.player.get_position_ms()
        pos_sec = None if position is None else int(position / 1000)
        logger.info(
            "Heartbeat state=%s track_index=%s title=%s pos_sec=%s viz=%s",
            state,
            track_index,
            title,
            pos_sec,
            self._viz_name,
        )

    def _set_message(
        self,
        text: str,
        *,
        level: str = "info",
        timeout: Optional[float] = None,
    ) -> None:
        self._status_controller.show_message(text, level=level, timeout=timeout)

    def _save_config(self) -> None:
        self._config = AppConfig(
            last_open_path=str(self._last_open_path)
            if self._last_open_path
            else None,
            open_recursive=self._open_recursive,
            volume=self._volume,
            repeat_mode=self._repeat_mode,
            shuffle=self._shuffle,
            viz_name=self._viz_name,
            ansi_colors=self._ansi_colors,
        )
        save_config(self._config)

    def _render_status(self) -> Text:
        if not self._status:
            return Text("")
        max_width = max(1, self._status.size.width)
        return self._status_controller.render_line(max_width, focused=self.focused)

    def _render_modes(self) -> str:
        mode_map = {"off": "OFF", "one": "ONE", "all": "ALL"}
        repeat = mode_map.get(self._repeat_mode, "OFF")
        shuffle = "ON" if self._shuffle else "OFF"
        return f"R:{repeat} S:{shuffle}"

    def _render_repeat_label(self) -> Text:
        mode_map = {"off": "OFF", "one": "ONE", "all": "ALL"}
        repeat = mode_map.get(self._repeat_mode, "OFF")
        if repeat == "OFF":
            return Text("R:OFF", style="#8a93a3")
        return Text(f"R:{repeat}", style="#9cff57")

    def _render_shuffle_label(self) -> Text:
        if self._shuffle:
            return Text("S:ON", style="#9cff57")
        return Text("S:OFF", style="#8a93a3")

    def _render_transport_label(self) -> Text:
        state = (self.player.get_state() or "").lower()
        return Text("[ PAUSE ]") if "playing" in state else Text("[ PLAY ] ")

    def _update_transport_row(self) -> None:
        try:
            label = self.query_one("#key_playpause", Button)
        except Exception:
            return
        label.label = self._render_transport_label()

    def _handle_transport_action(self, control_id: str) -> None:
        if control_id == "key_prev":
            self.action_previous_track()
        elif control_id == "key_playpause":
            self.action_toggle_playback()
        elif control_id == "key_stop":
            self.action_stop()
        elif control_id == "key_next":
            self.action_next_track()


    def _on_tick(self) -> None:
        self._progress_tick += 1
        if self._header:
            self._header.update(self._render_header())
        if (
            self._visualizer
            and not self._frame_player.is_running
            and self._last_visualizer_text is None
        ):
            self._visualizer.update(self._render_visualizer())
        if self._progress:
            self._progress.update(self._render_progress())
        self._update_transport_row()
        if self._status:
            self._status.update(self._render_status())
        self._update_visualizer_hud()
        if self._progress_tick == 1:
            self._update_playlist_view()
        if self.player.consume_end_reached():
            self._advance_track(auto=True)

    def _render_header(self) -> str:
        title = self._filename
        if self.playlist and not self.playlist.is_empty():
            track = self.playlist.current()
            if track:
                title = track.title
        return f"RhythmSlicer Pro | {title}"

    def _render_visualizer(self) -> str:
        width, height = self._visualizer_viewport()
        if width <= 0 or height <= 0:
            return ""
        if width <= 2 or height <= 1:
            return self._tiny_visualizer_text(width, height)
        if not self.playlist or self.playlist.is_empty():
            message = "No tracks loaded"
            pad = max(0, (width - len(message)) // 2)
            line = (" " * pad + message).ljust(width)
            return "\n".join(line for _ in range(height))
        message = "Visualizer idle"
        pad = max(0, (width - len(message)) // 2)
        line = (" " * pad + message).ljust(width)
        return "\n".join(line for _ in range(height))

    def _render_visualizer_hud(self) -> str:
        width, height = self._visualizer_hud_size()
        if width <= 0 or height <= 0:
            return ""
        title = "No track"
        artist = "--"
        if self.playlist and not self.playlist.is_empty():
            track = self.playlist.current()
            if track:
                meta = get_track_meta(track.path)
                if meta.title:
                    title = meta.title
                else:
                    title = track.title
                if meta.artist:
                    artist = meta.artist
        state = _display_state(self.player.get_state())
        position = _format_time_ms(self.player.get_position_ms())
        length = _format_time_ms(self.player.get_length_ms())
        timing = f"{position or '--:--'} / {length or '--:--'}"
        left_lines = [f"TITLE: {title}", f"ARTIST: {artist}"]
        right_lines = [f"STATE: {state}", f"TIME: {timing}", f"VOL: {self._volume}"]
        gap = 2
        min_col = 18
        use_two_cols = width >= (min_col * 2 + gap)
        if use_two_cols:
            left_width = max(min_col, (width - gap) // 2)
            right_width = max(min_col, width - gap - left_width)
            rows = max(height, len(left_lines), len(right_lines))
            left_lines = left_lines + [""] * max(0, rows - len(left_lines))
            right_lines = right_lines + [""] * max(0, rows - len(right_lines))
            lines = []
            for idx in range(rows):
                left = _truncate_line(left_lines[idx], left_width).ljust(left_width)
                right = _truncate_line(right_lines[idx], right_width).ljust(right_width)
                lines.append(f"{left}{' ' * gap}{right}")
        else:
            lines = [
                f"TITLE: {title}",
                f"ARTIST: {artist}",
                f"STATE: {state}",
                f"TIME: {timing} | VOL: {self._volume}",
            ]
        if len(lines) < height:
            lines.extend([""] * (height - len(lines)))
        if len(lines) > height:
            lines = lines[:height]
        return "\n".join(_truncate_line(line, width).ljust(width) for line in lines)

    def _visualizer_hud_size(self) -> tuple[int, int]:
        if not self._visualizer_hud:
            return (1, 1)
        size = (
            getattr(self._visualizer_hud, "content_size", None)
            or self._visualizer_hud.size
        )
        width = max(1, getattr(size, "width", 1))
        height = max(1, getattr(size, "height", 1))
        return (width, height)

    def _update_visualizer_hud(self) -> None:
        if self._visualizer_hud:
            self._visualizer_hud.update(self._render_visualizer_hud())

    def _render_progress(self) -> str:
        if not self._progress:
            return ""
        size = getattr(self._progress, "size", None)
        width = max(1, getattr(size, "width", 1) if size else 1)
        length = self.player.get_length_ms()
        if not length or length <= 0:
            bar = ["-"] * width
            pulse = self._progress_tick % max(1, width)
            bar[pulse] = "="
            return "".join(bar)
        position = self.player.get_position_ms() or 0
        ratio = min(1.0, max(0.0, position / float(length)))
        filled = int(ratio * width)
        return "=" * filled + "-" * max(0, width - filled)

    async def _populate_playlist(self) -> None:
        if not self._playlist_list or self.playlist is None:
            return
        self._update_playlist_view()

    def _sync_selection(self) -> None:
        if not self._playlist_list or not self.playlist or self.playlist.is_empty():
            return
        self._update_playlist_view()

    async def set_playlist(
        self, playlist: Playlist, *, preserve_path: Optional[Path]
    ) -> None:
        """Replace the current playlist and refresh UI state."""
        self.playlist = playlist
        self._scroll_offset = 0
        if preserve_path and playlist.tracks:
            for idx, track in enumerate(playlist.tracks):
                if track.path == preserve_path:
                    playlist.set_index(idx)
                    break
            else:
                playlist.set_index(0)
        elif playlist.tracks:
            playlist.set_index(0)
        self._reset_play_order()
        await self._populate_playlist()
        self._sync_selection()

    async def set_playlist_from_open(
        self, playlist: Playlist, source_path: Path
    ) -> None:
        self.playlist = playlist
        self.playlist.set_index(0)
        self._filename = source_path.name
        self._scroll_offset = 0
        self._reset_play_order()
        await self._populate_playlist()
        self._sync_selection()
        self._last_open_path = source_path
        if not self._play_current_track():
            self._skip_failed_track()

    def _play_current_track(self) -> bool:
        if not self.playlist or self.playlist.is_empty():
            return False
        track = self.playlist.current()
        if not track:
            return False
        try:
            self.player.load(str(track.path))
            self.player.play()
        except Exception:
            logger.exception("Playback failed for %s", track.path)
            self._set_message(f"Failed to play: {track.title}", level="error")
            return False
        self._playing_index = self.playlist.index
        logger.info("Track change index=%s path=%s", self.playlist.index, track.path)
        self._sync_selection()
        self._start_hackscript(
            track.path,
            playback_pos_ms=self._get_playback_position_ms(),
            playback_state=self._get_playback_state(),
        )
        self._update_visualizer_hud()
        return True

    def _advance_track(self, auto: bool = False) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        if auto and self._repeat_mode == "one":
            self._play_current_track()
            return
        wrap = self._repeat_mode == "all"
        next_index = self._next_index(wrap=wrap)
        if next_index is None:
            if auto and self._repeat_mode == "off":
                self.player.stop()
                self._stop_hackscript()
            self._set_message("End of playlist")
            return
        self._set_selected(next_index)
        if not self._play_current_track():
            self._skip_failed_track()

    def _skip_failed_track(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        attempts = len(self.playlist.tracks)
        while attempts > 0:
            track = self.playlist.next()
            if track is None:
                break
            if self._play_current_track():
                return
            attempts -= 1
        self.player.stop()
        self._stop_hackscript()

    def _try_seek(self, delta_ms: int) -> bool:
        seek = getattr(self.player, "seek_ms", None)
        if callable(seek):
            if seek(delta_ms):
                return True
        self._set_message("Seek unsupported", level="warn")
        return False

    def _get_playback_position_ms(self) -> int | None:
        getter = getattr(self.player, "get_position_ms", None)
        if not callable(getter):
            return None
        try:
            return getter()
        except Exception:
            return None

    def _get_playback_state(self) -> str:
        state = (self.player.get_state() or "").lower()
        if "paused" in state:
            return "paused"
        return "playing"

    def _restart_hackscript_from_player(self) -> None:
        if self._viz_restart_timer is not None:
            stopper = getattr(self._viz_restart_timer, "stop", None)
            if callable(stopper):
                stopper()
            self._viz_restart_timer = None
        if not self._current_track_path:
            return
        pos_ms = self._get_playback_position_ms()
        state = self._get_playback_state()
        self._restart_hackscript(
            playback_pos_ms=pos_ms,
            playback_state=state,
        )

    def _schedule_viz_restart(self, delay: float = 0.2) -> None:
        if not self._current_track_path:
            return
        if self._viz_restart_timer is not None:
            stopper = getattr(self._viz_restart_timer, "stop", None)
            if callable(stopper):
                stopper()
        self._viz_restart_timer = self.set_timer(
            delay, self._restart_hackscript_from_player
        )

    def _seek_to_ratio(self, ratio: float) -> bool:
        length = self.player.get_length_ms()
        if not length or length <= 0:
            self._set_message("Seek unsupported", level="warn")
            return False
        set_ratio = getattr(self.player, "set_position_ratio", None)
        if callable(set_ratio):
            if set_ratio(ratio):
                self._schedule_viz_restart()
                return True
        position = self.player.get_position_ms() or 0
        target = target_ms_from_ratio(length, ratio)
        delta = target - position
        seek = getattr(self.player, "seek_ms", None)
        if callable(seek):
            if seek(delta):
                self._schedule_viz_restart()
                return True
        self._set_message("Seek unsupported", level="warn")
        return False

    def action_toggle_playback(self) -> None:
        state = (self.player.get_state() or "").lower()
        if "playing" in state:
            self.player.pause()
            self._set_message("Paused")
            desired_state = "paused"
            logger.info("Playback paused")
        elif "paused" in state:
            self.player.play()
            self._set_message("Playing")
            desired_state = "playing"
            logger.info("Playback resumed")
        else:
            if self.playlist and not self.playlist.is_empty():
                if self._play_current_track():
                    self._set_message("Playing")
                    logger.info("Playback started")
                    return
                return
            self.player.play()
            self._set_message("Playing")
            desired_state = "playing"
            logger.info("Playback started")
        pos_ms = self._get_playback_position_ms()
        self._restart_hackscript(
            playback_pos_ms=pos_ms,
            playback_state=desired_state,
        )
        self._update_visualizer_hud()

    def action_stop(self) -> None:
        self.player.stop()
        self._playing_index = None
        self._stop_hackscript()
        self._set_message("Stopped")
        logger.info("Playback stopped")
        self._update_visualizer_hud()

    def action_seek_back(self) -> None:
        if self._try_seek(-5000):
            self._schedule_viz_restart()
        self._update_visualizer_hud()

    def action_seek_forward(self) -> None:
        if self._try_seek(5000):
            self._schedule_viz_restart()
        self._update_visualizer_hud()

    def action_volume_up(self) -> None:
        self._volume = min(100, self._volume + 5)
        self.player.set_volume(self._volume)
        self._set_message("Volume up")
        self._save_config()
        self._update_visualizer_hud()

    def action_volume_down(self) -> None:
        self._volume = max(0, self._volume - 5)
        self.player.set_volume(self._volume)
        self._set_message("Volume down")
        self._save_config()
        self._update_visualizer_hud()

    def action_next_track(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        next_index = self._next_index(wrap=self._repeat_mode == "all")
        if next_index is None:
            self._set_message("End of playlist")
            return
        self._set_selected(next_index)
        if not self._play_current_track():
            self._skip_failed_track()

    def action_previous_track(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        prev_index = self._prev_index(wrap=self._repeat_mode == "all")
        if prev_index is None:
            self._set_message("Start of playlist")
            return
        self._set_selected(prev_index)
        if not self._play_current_track():
            self._skip_failed_track()

    def action_quit_app(self) -> None:
        logger.info("TUI exit requested")
        self.player.stop()
        self._stop_hackscript()
        self._save_config()
        if self._hang_watchdog:
            self._hang_watchdog.stop()
        self.exit()

    def action_dump_threads(self) -> None:
        self._set_message("Dumping threads")
        logger.info("Manual thread dump requested")
        dump_threads("manual dump")

    def action_show_help(self) -> None:
        self.push_screen(HelpModal(self.BINDINGS))

    def on_shutdown(self) -> None:
        logger.info("TUI shutdown")
        if self._hang_watchdog:
            self._hang_watchdog.stop()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "repeat_toggle":
            self.action_cycle_repeat()
        elif event.button.id == "shuffle_toggle":
            self.action_toggle_shuffle()
        elif event.button.id:
            self._handle_transport_action(event.button.id)

    def action_move_up(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(max(0, self.playlist.index - 1))

    def action_move_down(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(min(len(self.playlist.tracks) - 1, self.playlist.index + 1))

    def action_play_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        try:
            focused = self.focused
        except Exception:
            focused = self._playlist_list
        if focused is not None and focused is not self._playlist_list:
            return
        self._play_selected()

    def action_remove_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        if self.playlist.index < 0 or self.playlist.index >= len(self.playlist.tracks):
            self.playlist.clamp_index()
            self._update_playlist_view()
            return
        selected_index = self.playlist.index
        removed_track = self.playlist.tracks[selected_index]
        playing_index = (
            self._playing_index if self._playing_index is not None else self.playlist.index
        )
        was_playing = selected_index == playing_index
        self.playlist.remove(selected_index)
        self._reset_play_order()
        if self.playlist.is_empty():
            if self._playlist_list:
                self._playlist_list.update("No tracks loaded")
            if was_playing:
                self.player.stop()
                self._playing_index = None
                self._stop_hackscript()
                self._set_message("Playlist empty")
            else:
                self._set_message(f"Removed: {removed_track.title}")
            return
        self._update_playlist_view()
        if was_playing:
            if not self._play_current_track():
                self._skip_failed_track()
        self._set_message(f"Removed: {removed_track.title}")

    def action_cycle_repeat(self) -> None:
        modes = ["off", "one", "all"]
        current = modes.index(self._repeat_mode)
        self._repeat_mode = modes[(current + 1) % len(modes)]
        self._set_message(f"Repeat: {self._repeat_mode}")
        self._update_playlist_view()
        self._save_config()

    def action_toggle_shuffle(self) -> None:
        self._shuffle = not self._shuffle
        self._reset_play_order()
        self._set_message(f"Shuffle: {'on' if self._shuffle else 'off'}")
        self._update_playlist_view()
        self._save_config()

    async def action_select_visualization(self) -> None:
        choices = self._list_visualizations()
        result = await self.push_screen_wait(
            VizPrompt(self._viz_name, choices)
        )
        if not result:
            return
        selection = result.strip()
        if selection not in choices:
            self._set_message("Unknown visualization", level="warn")
            return
        self._viz_name = selection
        self._save_config()
        if self._current_track_path:
            self._restart_hackscript_from_player()
        self._set_message(f"Visualization: {selection}")
        logger.info("Visualization set to %s", selection)

    async def action_save_playlist(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks to save", level="warn")
            return
        self.run_worker(self._save_playlist_flow(), exclusive=True)

    async def action_load_playlist(self) -> None:
        self.run_worker(self._load_playlist_flow(), exclusive=True)

    async def action_open(self) -> None:
        self.run_worker(self._open_flow(), exclusive=True)

    def _render_playlist_line_text(
        self,
        width: int,
        *,
        index: int,
        title: str,
        is_active: bool,
    ) -> Text:
        prefix = f"{'>>' if is_active else '  '} {index + 1:>3}  "
        title_space = max(1, width - len(prefix))
        if len(title) > title_space:
            title = title[: max(1, title_space - 1)] + "…"
        else:
            title = title.ljust(title_space)
        if is_active:
            line = Text(prefix + title, style="bold #5fc9d6 on #0c2024")
        else:
            line = Text()
            line.append(prefix[:3])
            line.append(prefix[3:6], style="#5b6170")
            line.append(prefix[6:])
            line.append(title, style="#8a93a3")
        if line.cell_len > width:
            line.truncate(width, overflow="ellipsis")
        if line.cell_len < width:
            pad_style = "bold #5fc9d6 on #0c2024" if is_active else "#8a93a3"
            line.append(" " * (width - line.cell_len), style=pad_style)
        return line

    def _update_playlist_view(self) -> None:
        if not self._playlist_list or not self.playlist:
            return
        width = self._playlist_width()
        view_height = self._playlist_view_height()
        if self.playlist.is_empty():
            message = _truncate_line("No tracks loaded", width)
            self._playlist_list.update(message)
            self._update_playlist_footer()
            return
        lines: list[Text] = []
        for idx, track in enumerate(self.playlist.tracks):
            is_active = idx == self.playlist.index
            line = self._render_playlist_line_text(
                width,
                index=idx,
                title=track.title,
                is_active=is_active,
            )
            lines.append(line)
        max_offset = max(0, len(lines) - view_height)
        self._scroll_offset = min(self._scroll_offset, max_offset)
        if self.playlist.index < self._scroll_offset:
            self._scroll_offset = self.playlist.index
        elif self.playlist.index >= self._scroll_offset + view_height:
            self._scroll_offset = self.playlist.index - view_height + 1
        start = max(0, min(self._scroll_offset, max_offset))
        end = start + view_height
        visible = lines[start:end]
        if len(visible) < view_height:
            visible.extend([Text("")] * (view_height - len(visible)))
        output = Text()
        for idx, line in enumerate(visible):
            if idx:
                output.append("\n")
            output.append_text(line)
        self._playlist_list.update(output)
        self._update_playlist_footer()

    def _render_playlist_footer(self) -> str:
        if not self.playlist or self.playlist.is_empty():
            current = "--"
            total = 0
        else:
            current = str(self.playlist.index + 1)
            total = len(self.playlist.tracks)
        text = f"Track: {current}/{total}"
        return _truncate_line(text, self._playlist_width())

    def _update_playlist_footer(self) -> None:
        if not self._playlist_list:
            return
        track = self.query_one("#playlist_footer_track", Static)
        repeat = self.query_one("#repeat_toggle", Button)
        shuffle = self.query_one("#shuffle_toggle", Button)
        track.update(self._render_playlist_footer())
        repeat.label = self._render_repeat_label()
        shuffle.label = self._render_shuffle_label()

    def _playlist_width(self) -> int:
        if not self._playlist_list:
            return 40
        size = getattr(self._playlist_list, "content_size", None) or getattr(
            self._playlist_list, "size", None
        )
        width = getattr(size, "width", 0) if size else 0
        return max(30, width)

    def _playlist_view_height(self) -> int:
        if not self._playlist_list:
            return 1
        size = getattr(self._playlist_list, "content_size", None) or getattr(
            self._playlist_list, "size", None
        )
        height = getattr(size, "height", 0) if size else 0
        if height <= 0 and self.playlist:
            height = len(self.playlist.tracks)
        return max(1, height)

    def _row_to_index(self, row: int) -> Optional[int]:
        if not self.playlist or self.playlist.is_empty():
            return None
        view_height = self._playlist_view_height()
        if row < 0 or row >= view_height:
            return None
        index = self._scroll_offset + row
        if index >= len(self.playlist.tracks):
            return None
        return index

    def _set_selected(self, index: int) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        index = max(0, min(index, len(self.playlist.tracks) - 1))
        self.playlist.set_index(index)
        self._sync_play_order_pos()
        self._update_playlist_view()

    def _play_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        self._sync_play_order_pos()
        if not self._play_current_track():
            self._skip_failed_track()
        self._sync_selection()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if self._progress and getattr(self._progress, "region", None):
            region = self._progress.region
            sx = getattr(event, "screen_x", event.x)
            sy = getattr(event, "screen_y", event.y)
            if region.contains(sx, sy):
                ratio = ratio_from_click(int(sx - region.x), region.width)
                self._seek_to_ratio(ratio)
                self._scrub_active = True
                event.stop()
                return
        if not self._playlist_list:
            return
        region = getattr(self._playlist_list, "region", None)
        sx = getattr(event, "screen_x", event.x)
        sy = getattr(event, "screen_y", event.y)
        if region and not region.contains(sx, sy):
            return
        row = (
            int(sy - region.y)
            if region
            else int(getattr(event, "offset_y", event.y))
        )
        index = self._row_to_index(row)
        if index is None:
            return
        self.set_focus(self._playlist_list)
        now = self._now()
        if (
            self._last_click_index == index
            and now - self._last_click_time <= 0.4
        ):
            self._set_selected(index)
            self._play_selected()
        else:
            self._set_selected(index)
        self._last_click_index = index
        self._last_click_time = now

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if not self._scrub_active or not self._progress:
            return
        region = getattr(self._progress, "region", None)
        if not region:
            return
        sx = getattr(event, "screen_x", event.x)
        sy = getattr(event, "screen_y", event.y)
        if not region.contains(sx, sy):
            return
        ratio = ratio_from_click(int(sx - region.x), region.width)
        self._seek_to_ratio(ratio)
        event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._scrub_active:
            self._scrub_active = False
            event.stop()

    def on_resize(self, event: events.Resize) -> None:
        del event
        self._update_visualizer_viewport()
        self._update_playlist_view()
        self._update_visualizer_hud()
        if self._current_track_path:
            self._restart_hackscript_from_player()
            self._set_message("Visualizer restarted (resize)")
        elif self._visualizer and not self._frame_player.is_running:
            self._visualizer.update(self._render_visualizer())


    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if not self._playlist_list:
            return
        region = getattr(self._playlist_list, "region", None)
        sx = getattr(event, "screen_x", event.x)
        sy = getattr(event, "screen_y", event.y)
        if region and not region.contains(sx, sy):
            return
        max_offset = (
            max(0, len(self.playlist.tracks) - self._playlist_view_height())
            if self.playlist
            else 0
        )
        self._scroll_offset = min(self._scroll_offset + 1, max_offset)
        self._update_playlist_view()
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if not self._playlist_list:
            return
        region = getattr(self._playlist_list, "region", None)
        sx = getattr(event, "screen_x", event.x)
        sy = getattr(event, "screen_y", event.y)
        if region and not region.contains(sx, sy):
            return
        self._scroll_offset = max(0, self._scroll_offset - 1)
        self._update_playlist_view()
        event.stop()

    def _reset_play_order(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._play_order = []
            self._play_order_pos = -1
            return
        self._play_order, self._play_order_pos = build_play_order(
            len(self.playlist.tracks),
            self.playlist.index,
            self._shuffle,
            self._rng,
        )

    def _sync_play_order_pos(self) -> None:
        if not self.playlist or not self._play_order:
            return
        try:
            self._play_order_pos = self._play_order.index(self.playlist.index)
        except ValueError:
            self._play_order_pos = 0

    def _next_index(self, *, wrap: bool) -> Optional[int]:
        if not self._play_order:
            return None
        if self._play_order_pos < 0:
            self._sync_play_order_pos()
        next_pos = self._play_order_pos + 1
        if next_pos >= len(self._play_order):
            if not wrap:
                return None
            next_pos = 0
        self._play_order_pos = next_pos
        return self._play_order[next_pos]

    def _prev_index(self, *, wrap: bool) -> Optional[int]:
        if not self._play_order:
            return None
        if self._play_order_pos < 0:
            self._sync_play_order_pos()
        prev_pos = self._play_order_pos - 1
        if prev_pos < 0:
            if not wrap:
                return None
            prev_pos = len(self._play_order) - 1
        self._play_order_pos = prev_pos
        return self._play_order[prev_pos]

    def _default_save_path(self) -> Path:
        if self._last_playlist_path:
            return self._last_playlist_path
        if self.playlist and self.playlist.current():
            return self.playlist.current().path.parent / "playlist.m3u8"
        return Path.cwd() / "playlist.m3u8"

    async def _save_playlist_flow(self) -> None:
        default_path = self._default_save_path()
        result = await self.push_screen_wait(
            PlaylistPrompt(
                "Save Playlist",
                str(default_path),
                show_absolute_toggle=True,
                absolute_default=False,
            )
        )
        if not result:
            return
        dest_str, absolute = _parse_prompt_result(result)
        dest = Path(dest_str).expanduser()
        try:
            from rhythm_slicer.playlist_io import save_m3u8

            save_m3u8(self.playlist, dest, mode="absolute" if absolute else "auto")
        except Exception as exc:
            logger.exception("Save playlist failed: %s", dest)
            self._set_message(f"Save failed: {exc}", level="error")
            return
        self._last_playlist_path = dest
        self._set_message(f"Saved playlist: {dest}")
        logger.info("Playlist saved to %s", dest)

    async def _load_playlist_flow(self) -> None:
        default = str(self._last_playlist_path) if self._last_playlist_path else ""
        result = await self.push_screen_wait(PlaylistPrompt("Load Playlist", default))
        if not result:
            return
        path_str, _ = _parse_prompt_result(result)
        path = Path(path_str).expanduser()
        try:
            new_playlist = load_from_input(path)
        except Exception as exc:
            logger.exception("Load playlist failed: %s", path)
            self._set_message(f"Load failed: {exc}", level="error")
            return
        if new_playlist.is_empty():
            self._set_message("Playlist is empty", level="warn")
            return
        preserve = self.playlist.current().path if self.playlist else None
        await self.set_playlist(new_playlist, preserve_path=preserve)
        self._last_playlist_path = path
        if not self._play_current_track():
            self._skip_failed_track()
        else:
            self._set_message(f"Loaded playlist: {path}")
            logger.info("Playlist loaded from %s", path)

    async def _open_flow(self) -> None:
        default = str(self._last_open_path) if self._last_open_path else ""
        result = await self.push_screen_wait(OpenPrompt(default, self._open_recursive))
        if not result:
            return
        path_str, recursive = _parse_open_prompt_result(result)
        await self._handle_open_path(path_str, recursive=recursive)

    async def _handle_open_path(self, path_str: str, *, recursive: bool = False) -> None:
        path = Path(path_str).expanduser()
        if not path.exists():
            self._set_message("Path not found", level="warn")
            return
        try:
            if recursive and path.is_dir():
                new_playlist = _load_recursive_directory(path)
            else:
                new_playlist = load_from_input(path)
        except Exception as exc:
            logger.exception("Open path failed: %s", path)
            self._set_message(f"Load failed: {exc}", level="error")
            return
        if new_playlist.is_empty():
            self._set_message("No supported audio files found", level="warn")
            return
        await self.set_playlist_from_open(new_playlist, source_path=path)
        self._last_open_path = path
        self._open_recursive = recursive
        self._save_config()
        suffix = " (recursive)" if recursive and path.is_dir() else ""
        self._set_message(f"Loaded {len(new_playlist.tracks)} tracks{suffix}")
        logger.info("Tracks loaded count=%s path=%s", len(new_playlist.tracks), path)

    def _visualizer_viewport(self) -> tuple[int, int]:
        if not self._visualizer:
            return (1, 1)
        size = getattr(self._visualizer, "content_size", None) or self._visualizer.size
        width = max(1, getattr(size, "width", 1))
        height = max(1, getattr(size, "height", 1))
        return (width, height)

    def _update_visualizer_viewport(self) -> None:
        width, height = self._visualizer_viewport()
        self._viewport_width = width
        self._viewport_height = height

    def _tiny_visualizer_text(self, width: int, height: int) -> str:
        message = "Visualizer too small"
        line = _truncate_line(message, width).ljust(width)
        lines = [line] + [" " * width for _ in range(max(0, height - 1))]
        return "\n".join(lines)

    def _clip_frame_text(self, text: str, width: int, height: int) -> str:
        if width <= 0 or height <= 0:
            return ""
        lines = text.splitlines()
        if not lines:
            lines = [""]
        clipped: list[str] = []
        for idx in range(height):
            line = lines[idx] if idx < len(lines) else ""
            if len(line) > width:
                line = line[:width]
            clipped.append(line.ljust(width))
        return "\n".join(clipped)

    def _render_ansi_frame(self, text: str, width: int, height: int) -> Text:
        sanitized = sanitize_ansi_sgr(text)
        lines = sanitized.splitlines()
        if not lines:
            lines = [""]
        rendered = Text()
        for idx in range(height):
            if idx > 0:
                rendered.append("\n")
            line = lines[idx] if idx < len(lines) else ""
            line_text = Text.from_ansi(line)
            if line_text.cell_len > width:
                line_text.truncate(width)
            if line_text.cell_len < width:
                line_text.append(" " * (width - line_text.cell_len))
            rendered.append_text(line_text)
        return rendered

    def _show_frame(self, frame: HackFrame) -> None:
        if not self._visualizer:
            return
        width, height = self._visualizer_viewport()
        if width <= 2 or height <= 1:
            text = self._tiny_visualizer_text(width, height)
            self._last_visualizer_text = text
            self._visualizer.update(text)
            return
        use_ansi = bool(self._viz_prefs.get("ansi_colors", False))
        if use_ansi:
            rendered = self._render_ansi_frame(frame.text, width, height)
            self._last_visualizer_text = rendered.plain
            self._visualizer.update(rendered)
        else:
            clipped = self._clip_frame_text(frame.text, width, height)
            self._last_visualizer_text = clipped
            self._visualizer.update(clipped)

    def _start_hackscript(
        self,
        track_path: Path,
        *,
        playback_pos_ms: int | None = None,
        playback_state: str = "playing",
    ) -> None:
        self._update_visualizer_viewport()
        resolved = track_path.expanduser().resolve()
        self._current_track_path = resolved
        if playback_pos_ms is None:
            playback_pos_ms = 0
        prefs = {
            "show_absolute_paths": False,
            "viz": self._viz_name,
            "ansi_colors": self._ansi_colors,
            "playback_pos_ms": playback_pos_ms,
            "playback_state": playback_state,
        }
        self._viz_prefs = dict(prefs)
        logger.info(
            "Visualizer start name=%s size=%sx%s",
            self._viz_name,
            self._viewport_width,
            self._viewport_height,
        )
        frames = generate_hackscript(
            resolved,
            (self._viewport_width, self._viewport_height),
            prefs,
            viz_name=self._viz_name,
        )
        self._frame_player.start(frames)

    def _restart_hackscript(
        self,
        *,
        playback_pos_ms: int | None = None,
        playback_state: str = "playing",
    ) -> None:
        if not self._current_track_path:
            return
        logger.info("Visualizer restart name=%s", self._viz_name)
        self._start_hackscript(
            self._current_track_path,
            playback_pos_ms=playback_pos_ms,
            playback_state=playback_state,
        )

    def _stop_hackscript(self) -> None:
        self._frame_player.stop()
        self._current_track_path = None
        self._last_visualizer_text = None
        self._viz_prefs = {}
        logger.info("Visualizer stop")
        if self._viz_restart_timer is not None:
            stopper = getattr(self._viz_restart_timer, "stop", None)
            if callable(stopper):
                stopper()
            self._viz_restart_timer = None
        if self._visualizer:
            self._visualizer.update(self._render_visualizer())

    def _list_visualizations(self) -> list[str]:
        try:
            package = importlib.import_module("rhythm_slicer.visualizations")
        except Exception:
            return [self._viz_name or "hackscope"]
        names: list[str] = []
        for module_info in pkgutil.iter_modules(package.__path__):
            name = module_info.name
            try:
                module = importlib.import_module(
                    f"rhythm_slicer.visualizations.{name}"
                )
            except Exception:
                continue
            viz_name = getattr(module, "VIZ_NAME", None)
            if isinstance(viz_name, str) and callable(
                getattr(module, "generate_frames", None)
            ):
                names.append(viz_name)
        if not names:
            return [self._viz_name or "hackscope"]
        return sorted(set(names))


class PlaylistPrompt(ModalScreen[Optional[str]]):
    """Modal prompt for playlist paths."""

    def __init__(
        self,
        title: str,
        default_path: str,
        *,
        show_absolute_toggle: bool = False,
        absolute_default: bool = False,
    ) -> None:
        super().__init__()
        self._title = title
        self._default_path = default_path
        self._show_absolute_toggle = show_absolute_toggle
        self._absolute_default = absolute_default

    def compose(self) -> ComposeResult:
        with Container(id="playlist_prompt"):
            yield Static(self._title, id="prompt_title")
            yield Input(value=self._default_path, id="prompt_input")
            if self._show_absolute_toggle:
                toggle = Button(
                    "Save absolute paths: Off",
                    id="prompt_absolute",
                )
                if self._absolute_default:
                    toggle.label = "Save absolute paths: On"
                yield toggle
            with Horizontal(id="prompt_buttons"):
                yield Button("OK", id="prompt_ok")
                yield Button("Cancel", id="prompt_cancel")

    def on_mount(self) -> None:
        self.query_one("#prompt_input", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prompt_absolute":
            label = event.button.label
            event.button.label = (
                "Save absolute paths: Off"
                if "On" in label
                else "Save absolute paths: On"
            )
            return
        if event.button.id == "prompt_ok":
            value = self.query_one("#prompt_input", Input).value.strip()
            absolute = False
            toggle = self.query("#prompt_absolute")
            if toggle:
                button = toggle.first()
                if button and isinstance(button, Button):
                    absolute = "On" in button.label
            if value:
                self.dismiss(f"{value}::abs={int(absolute)}")
            else:
                self.dismiss(None)
        else:
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
        if event.key == "enter":
            value = self.query_one("#prompt_input", Input).value.strip()
            absolute = False
            toggle = self.query("#prompt_absolute")
            if toggle:
                button = toggle.first()
                if button and isinstance(button, Button):
                    absolute = "On" in button.label
            if value:
                self.dismiss(f"{value}::abs={int(absolute)}")
            else:
                self.dismiss(None)


class VizPrompt(ModalScreen[Optional[str]]):
    """Modal prompt for selecting a visualization."""

    def __init__(self, current: str, choices: list[str]) -> None:
        super().__init__()
        self._current = current
        self._choices = choices

    def compose(self) -> ComposeResult:
        with Container(id="playlist_prompt"):
            yield Static("Visualization", id="prompt_title")
            options = "Available: " + ", ".join(self._choices)
            yield Static(options, id="prompt_hint")
            yield Input(value=self._current, id="prompt_input")
            with Horizontal(id="prompt_buttons"):
                yield Button("OK", id="prompt_ok")
                yield Button("Cancel", id="prompt_cancel")

    def on_mount(self) -> None:
        self.query_one("#prompt_input", Input).focus()

    def _confirm(self) -> None:
        value = self.query_one("#prompt_input", Input).value.strip()
        if value:
            self.dismiss(value)
        else:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prompt_ok":
            self._confirm()
        else:
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key == "enter":
            if isinstance(self.app.focused, Input):
                self._confirm()


class OpenPrompt(ModalScreen[Optional[str]]):
    """Modal prompt for opening a path."""

    def __init__(self, default_path: str, recursive_default: bool) -> None:
        super().__init__()
        self._default_path = default_path
        self._recursive = recursive_default

    def compose(self) -> ComposeResult:
        with Container(id="playlist_prompt"):
            yield Static("Open", id="prompt_title")
            yield Input(value=self._default_path, id="prompt_input")
            yield Static(
                "Enter a folder, audio file, or .m3u/.m3u8 playlist path",
                id="prompt_hint",
            )
            label = (
                "Load subfolders recursively: On"
                if self._recursive
                else "Load subfolders recursively: Off"
            )
            yield Button(label, id="prompt_recursive")
            with Horizontal(id="prompt_buttons"):
                yield Button("Open", id="prompt_open")
                yield Button("Cancel", id="prompt_cancel")

    def on_mount(self) -> None:
        self.query_one("#prompt_input", Input).focus()

    def _toggle_recursive(self) -> None:
        self._recursive = not self._recursive
        label = (
            "Load subfolders recursively: On"
            if self._recursive
            else "Load subfolders recursively: Off"
        )
        self.query_one("#prompt_recursive", Button).label = label

    def _confirm(self) -> None:
        value = self.query_one("#prompt_input", Input).value.strip()
        if value:
            self.dismiss(_format_open_prompt_result(value, self._recursive))
        else:
            self.dismiss(None)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "prompt_recursive":
            self._toggle_recursive()
            return
        if event.button.id == "prompt_open":
            self._confirm()
        else:
            self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            return
        if event.key == "ctrl+r":
            self._toggle_recursive()
            return
        if event.key == "enter":
            if isinstance(self.app.focused, Input):
                self._confirm()


def _truncate_line(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if len(text) <= max_width:
        return text
    if max_width <= 1:
        return text[:max_width]
    return text[: max_width - 1] + "…"


def _parse_prompt_result(value: str) -> tuple[str, bool]:
    if "::abs=" not in value:
        return value, False
    path, raw = value.rsplit("::abs=", 1)
    return path, raw.strip() == "1"


def _format_open_prompt_result(path: str, recursive: bool) -> str:
    return f"{path}::recursive={int(recursive)}"


def _parse_open_prompt_result(value: str) -> tuple[str, bool]:
    if "::recursive=" not in value:
        return value, False
    path, raw = value.rsplit("::recursive=", 1)
    return path, raw.strip() == "1"


def _load_recursive_directory(path: Path) -> Playlist:
    files = [
        entry
        for entry in path.rglob("*")
        if entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    files.sort(key=lambda entry: entry.relative_to(path).as_posix().lower())
    tracks = []
    for entry in files:
        meta = get_track_meta(entry)
        title = format_display_title(entry, meta)
        tracks.append(Track(path=entry, title=title))
    return Playlist(tracks)


def run_tui(path: str, player: VlcPlayer, *, viz_name: Optional[str] = None) -> int:
    """Run the TUI and return an exit code."""
    logger.info("TUI start path=%s viz=%s", path, viz_name)
    try:
        set_console_level(logging.WARNING)
    except Exception:
        logger.exception("Failed to set console log level for TUI")
    app = RhythmSlicerApp(player=player, path=path, viz_name=viz_name)
    app.run()
    logger.info("TUI exit")
    return 0
