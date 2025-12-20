"""Textual-based TUI for RhythmSlicer Pro."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random
from pathlib import Path
import time
from typing import Callable, Optional

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual import events
    from textual.screen import ModalScreen
    from textual.widgets import Button, Input, Static
except Exception as exc:  # pragma: no cover - depends on environment
    raise RuntimeError(
        "Textual is required for the TUI. Install the 'textual' dependency."
    ) from exc

from rhythm_slicer.config import AppConfig, load_config, save_config
from rhythm_slicer.player_vlc import VlcPlayer
from rhythm_slicer.playlist import Playlist, Track, load_from_input, SUPPORTED_EXTENSIONS


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
        Binding("ctrl+s", "save_playlist", "Save Playlist"),
        Binding("ctrl+o", "open", "Open"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        *,
        player: VlcPlayer,
        path: str,
        playlist: Optional[Playlist] = None,
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
        self._selection_index = 0
        self._scroll_offset = 0
        self._last_click_time = 0.0
        self._last_click_index: Optional[int] = None
        self._scrub_active = False
        self._repeat_mode = config.repeat_mode
        self._shuffle = config.shuffle
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
        self._message: Optional[TuiMessage] = None
        self._playing_index: Optional[int] = None
        self._header: Optional[Static] = None
        self._visualizer: Optional[Static] = None
        self._playlist_list: Optional[Static] = None
        self._progress: Optional[Static] = None
        self._status: Optional[Static] = None
        self._last_state: Optional[str] = None
        self._progress_tick = 0

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="header")
            with Container(id="main"):
                with Container(id="playlist_pane"):
                    with Vertical():
                        yield Static(id="playlist_list")
                        with Horizontal(id="playlist_footer"):
                            yield Static(id="playlist_footer_track")
                            yield Button("R:OFF", id="repeat_toggle")
                            yield Button("S:OFF", id="shuffle_toggle")
                yield Static(id="visualizer")
            yield Static(id="progress")
            yield Static(id="status")

    async def on_mount(self) -> None:
        self._header = self.query_one("#header", Static)
        self._visualizer = self.query_one("#visualizer", Static)
        self._playlist_list = self.query_one("#playlist_list", Static)
        self._playlist_list.can_focus = True
        playlist_pane = self.query_one("#playlist_pane", Container)
        playlist_pane.border_title = "Playlist"
        self._progress = self.query_one("#progress", Static)
        self._status = self.query_one("#status", Static)
        if self._visualizer:
            self._visualizer.border_title = "Visualizer"
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
        self.set_interval(0.1, self._on_tick)

    def _set_message(self, text: str, duration: float = 2.0) -> None:
        self._message = TuiMessage(text=text, until=self._now() + duration)

    def _save_config(self) -> None:
        self._config = AppConfig(
            last_open_path=str(self._last_open_path)
            if self._last_open_path
            else None,
            open_recursive=self._open_recursive,
            volume=self._volume,
            repeat_mode=self._repeat_mode,
            shuffle=self._shuffle,
        )
        save_config(self._config)

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
        track_info = "0/0"
        title = "No tracks"
        if self.playlist and not self.playlist.is_empty():
            track = self.playlist.current()
            if track:
                track_info = f"{self.playlist.index + 1}/{len(self.playlist.tracks)}"
                title = track.title
        hotkeys = "Keys: Space S ←/→ N/P Enter D Q + - R H Ctrl+S Ctrl+O"
        message = self._pop_message()
        track_count = len(self.playlist.tracks) if self.playlist else 0
        base = (
            f"State: {state} | Track: {track_info} {title} | "
            f"Time: {timing} | Vol: {self._volume} | {hotkeys} | Tracks: {track_count}"
        )
        line = f"{message} | {base}" if message else base
        if self._status:
            max_width = max(1, self._status.size.width)
            line = _truncate_line(line, max_width)
        return line

    def _render_modes(self) -> str:
        mode_map = {"off": "OFF", "one": "ONE", "all": "ALL"}
        repeat = mode_map.get(self._repeat_mode, "OFF")
        shuffle = "ON" if self._shuffle else "OFF"
        return f"R:{repeat} S:{shuffle}"

    def _render_repeat_label(self) -> str:
        mode_map = {"off": "OFF", "one": "ONE", "all": "ALL"}
        repeat = mode_map.get(self._repeat_mode, "OFF")
        return f"R:{repeat}"

    def _render_shuffle_label(self) -> str:
        return "S:ON" if self._shuffle else "S:OFF"

    def _on_tick(self) -> None:
        self._progress_tick += 1
        if self._header:
            self._header.update(self._render_header())
        if self._visualizer:
            self._visualizer.update(self._render_visualizer())
        if self._progress:
            self._progress.update(self._render_progress())
        if self._status:
            self._status.update(self._render_status())
        if self._progress_tick == 1:
            self._update_playlist_view()
        state = self.player.get_state()
        if state == "ended" and self._last_state != "ended":
            self._advance_track(auto=True)
        self._last_state = state

    def _render_header(self) -> str:
        title = self._filename
        if self.playlist and not self.playlist.is_empty():
            track = self.playlist.current()
            if track:
                title = track.title
        return f"RhythmSlicer Pro | {title}"

    def _render_visualizer(self) -> str:
        size = getattr(self._visualizer, "content_size", None) or self._visualizer.size
        width = max(1, size.width)
        height = max(1, size.height)
        if not self.playlist or self.playlist.is_empty():
            message = "No tracks loaded"
            pad = max(0, (width - len(message)) // 2)
            line = (" " * pad + message).ljust(width)
            return "\n".join(line for _ in range(height))
        position = self.player.get_position_ms()
        seed_ms = position if position is not None else int(time.time() * 1000)
        bars = visualizer_bars(seed_ms, width, height)
        return render_visualizer(bars, height)

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
        self._selection_index = 0
        if not self.playlist.is_empty():
            self._selection_index = self.playlist.index
        self._update_playlist_view()

    def _sync_selection(self) -> None:
        if not self._playlist_list or not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(self.playlist.index)

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
            self._set_message(f"Failed to play: {track.title}")
            return False
        self._playing_index = self.playlist.index
        self._sync_selection()
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

    def _try_seek(self, delta_ms: int) -> None:
        seek = getattr(self.player, "seek_ms", None)
        if callable(seek):
            if seek(delta_ms):
                return
        self._set_message("Seek unsupported")

    def _seek_to_ratio(self, ratio: float) -> None:
        length = self.player.get_length_ms()
        if not length or length <= 0:
            self._set_message("Seek unsupported")
            return
        set_ratio = getattr(self.player, "set_position_ratio", None)
        if callable(set_ratio):
            if set_ratio(ratio):
                return
        position = self.player.get_position_ms() or 0
        target = target_ms_from_ratio(length, ratio)
        delta = target - position
        seek = getattr(self.player, "seek_ms", None)
        if callable(seek):
            if seek(delta):
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
        self._playing_index = None
        self._set_message("Stopped")

    def action_seek_back(self) -> None:
        self._try_seek(-5000)

    def action_seek_forward(self) -> None:
        self._try_seek(5000)

    def action_volume_up(self) -> None:
        self._volume = min(100, self._volume + 5)
        self.player.set_volume(self._volume)
        self._set_message(f"Volume {self._volume}")
        self._save_config()

    def action_volume_down(self) -> None:
        self._volume = max(0, self._volume - 5)
        self.player.set_volume(self._volume)
        self._set_message(f"Volume {self._volume}")
        self._save_config()

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
        self.player.stop()
        self._save_config()
        self.exit()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "repeat_toggle":
            self.action_cycle_repeat()
        elif event.button.id == "shuffle_toggle":
            self.action_toggle_shuffle()

    def action_move_up(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(max(0, self._selection_index - 1), update_playlist=False)

    def action_move_down(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(
            min(len(self.playlist.tracks) - 1, self._selection_index + 1),
            update_playlist=False,
        )

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
        if self._selection_index < 0 or self._selection_index >= len(self.playlist.tracks):
            self._selection_index = max(
                0, min(self._selection_index, len(self.playlist.tracks) - 1)
            )
            self._update_playlist_view()
            return
        selected_index = self._selection_index
        removed_track = self.playlist.tracks[selected_index]
        playing_index = (
            self._playing_index if self._playing_index is not None else self.playlist.index
        )
        was_playing = selected_index == playing_index
        self.playlist.remove(selected_index)
        self._reset_play_order()
        if self.playlist.is_empty():
            self._selection_index = 0
            if self._playlist_list:
                self._playlist_list.update("No tracks loaded")
            if was_playing:
                self.player.stop()
                self._playing_index = None
                self._set_message("Playlist empty")
            else:
                self._set_message(f"Removed: {removed_track.title}")
            return
        self._selection_index = min(selected_index, len(self.playlist.tracks) - 1)
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

    async def action_save_playlist(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks to save")
            return
        self.run_worker(self._save_playlist_flow(), exclusive=True)

    async def action_load_playlist(self) -> None:
        self.run_worker(self._load_playlist_flow(), exclusive=True)

    async def action_open(self) -> None:
        self.run_worker(self._open_flow(), exclusive=True)

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
        lines = []
        for idx, track in enumerate(self.playlist.tracks):
            marker = "▶" if idx == self.playlist.index else " "
            selector = "➤" if idx == self._selection_index else " "
            prefix = f"{marker}{selector} {idx + 1:>3}  "
            title_space = max(1, width - len(prefix))
            title = track.title
            if len(title) > title_space:
                title = title[: max(1, title_space - 1)] + "…"
            else:
                title = title.ljust(title_space)
            lines.append(prefix + title)
        max_offset = max(0, len(lines) - view_height)
        self._scroll_offset = min(self._scroll_offset, max_offset)
        if self._selection_index < self._scroll_offset:
            self._scroll_offset = self._selection_index
        elif self._selection_index >= self._scroll_offset + view_height:
            self._scroll_offset = self._selection_index - view_height + 1
        start = max(0, min(self._scroll_offset, max_offset))
        end = start + view_height
        visible = lines[start:end]
        if len(visible) < view_height:
            visible.extend([""] * (view_height - len(visible)))
        self._playlist_list.update("\n".join(visible))
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

    def _set_selected(self, index: int, *, update_playlist: bool = True) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        index = max(0, min(index, len(self.playlist.tracks) - 1))
        self._selection_index = index
        if update_playlist:
            self.playlist.set_index(index)
            self._sync_play_order_pos()
        self._update_playlist_view()

    def _play_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        self.playlist.set_index(self._selection_index)
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
            self._set_message(f"Save failed: {exc}")
            return
        self._last_playlist_path = dest
        self._set_message(f"Saved playlist: {dest}")

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
            self._set_message(f"Load failed: {exc}")
            return
        if new_playlist.is_empty():
            self._set_message("Playlist is empty")
            return
        preserve = self.playlist.current().path if self.playlist else None
        await self.set_playlist(new_playlist, preserve_path=preserve)
        self._last_playlist_path = path
        if not self._play_current_track():
            self._skip_failed_track()
        else:
            self._set_message(f"Loaded playlist: {path}")

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
            self._set_message("Path not found")
            return
        try:
            if recursive and path.is_dir():
                new_playlist = _load_recursive_directory(path)
            else:
                new_playlist = load_from_input(path)
        except Exception as exc:
            self._set_message(f"Load failed: {exc}")
            return
        if new_playlist.is_empty():
            self._set_message("No supported audio files found")
            return
        await self.set_playlist_from_open(new_playlist, source_path=path)
        self._last_open_path = path
        self._open_recursive = recursive
        self._save_config()
        suffix = " (recursive)" if recursive and path.is_dir() else ""
        self._set_message(f"Loaded {len(new_playlist.tracks)} tracks{suffix}")


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
    tracks = [Track(path=entry, title=entry.name) for entry in files]
    return Playlist(tracks)


def run_tui(path: str, player: VlcPlayer) -> int:
    """Run the TUI and return an exit code."""
    app = RhythmSlicerApp(player=player, path=path)
    app.run()
    return 0
