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
    from textual import events
    from textual.widgets import Static
except Exception as exc:  # pragma: no cover - depends on environment
    raise RuntimeError(
        "Textual is required for the TUI. Install the 'textual' dependency."
    ) from exc

from rhythm_slicer.player_vlc import VlcPlayer
from rhythm_slicer.playlist import Playlist, Track, load_from_input


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
        Binding("up", "move_up", "Select Up"),
        Binding("down", "move_down", "Select Down"),
        Binding("n", "next_track", "Next"),
        Binding("p", "previous_track", "Previous"),
        Binding("enter", "play_selected", "Play Selected"),
        Binding("+", "volume_up", "Volume +5"),
        Binding("-", "volume_down", "Volume -5"),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        *,
        player: VlcPlayer,
        path: str,
        playlist: Optional[Playlist] = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__()
        self.player = player
        self.path = path
        self.playlist = playlist
        self._filename = Path(path).name
        self._volume = 100
        self._now = now
        self._selection_index = 0
        self._scroll_offset = 0
        self._last_click_time = 0.0
        self._last_click_index: Optional[int] = None
        self._message: Optional[TuiMessage] = None
        self._header: Optional[Static] = None
        self._visualizer: Optional[Static] = None
        self._playlist_list: Optional[Static] = None
        self._status: Optional[Static] = None
        self._last_state: Optional[str] = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="header")
            with Container(id="main"):
                yield Static(id="playlist_list")
                yield Static(id="visualizer")
            yield Static(id="status")

    async def on_mount(self) -> None:
        self._header = self.query_one("#header", Static)
        self._visualizer = self.query_one("#visualizer", Static)
        self._playlist_list = self.query_one("#playlist_list", Static)
        self._status = self.query_one("#status", Static)
        if self._visualizer:
            self._visualizer.border_title = "Visualizer"
        if self.playlist is None:
            self.playlist = load_from_input(Path(self.path))
        await self._populate_playlist()
        self._sync_selection()
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
        hotkeys = "Keys: Space S ←/→ N/P Enter Q + -"
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

    def _on_tick(self) -> None:
        if self._header:
            self._header.update(self._render_header())
        if self._visualizer:
            self._visualizer.update(self._render_visualizer())
        if self._status:
            self._status.update(self._render_status())
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

    async def _populate_playlist(self) -> None:
        if not self._playlist_list or self.playlist is None:
            return
        self._selection_index = 0
        if self.playlist.is_empty():
            self._playlist_list.update("No tracks loaded")
            return
        self._selection_index = self.playlist.index
        self._update_playlist_view()

    def _sync_selection(self) -> None:
        if not self._playlist_list or not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(self.playlist.index)

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
        self._sync_selection()
        return True

    def _advance_track(self, auto: bool = False) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        track = self.playlist.next()
        if track is None:
            if auto:
                self.player.stop()
            self._set_message("End of playlist")
            return
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
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        self._advance_track()
        self._sync_selection()

    def action_previous_track(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        track = self.playlist.prev()
        if track is None:
            self._set_message("Start of playlist")
            return
        if not self._play_current_track():
            self._skip_failed_track()
        self._sync_selection()

    def action_quit_app(self) -> None:
        self.player.stop()
        self.exit()

    def action_move_up(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(max(0, self._selection_index - 1))

    def action_move_down(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_selected(
            min(len(self.playlist.tracks) - 1, self._selection_index + 1)
        )

    def action_play_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        self._play_selected()

    def _update_playlist_view(self) -> None:
        if not self._playlist_list or not self.playlist:
            return
        width = self._playlist_width()
        lines: list[str] = []
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
        view_height = self._playlist_view_height()
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
        self._selection_index = index
        self.playlist.set_index(index)
        self._update_playlist_view()

    def _play_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        if not self._play_current_track():
            self._skip_failed_track()
        self._sync_selection()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if not self._playlist_list:
            return
        region = getattr(self._playlist_list, "region", None)
        if region and not region.contains(event.x, event.y):
            return
        row = (
            int(event.y - region.y + 1)
            if region
            else int(getattr(event, "offset_y", event.y) + 1)
        )
        index = self._row_to_index(row)
        if index is None:
            return
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

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if not self._playlist_list:
            return
        region = getattr(self._playlist_list, "region", None)
        if region and not region.contains(event.x, event.y):
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
        if region and not region.contains(event.x, event.y):
            return
        self._scroll_offset = max(0, self._scroll_offset - 1)
        self._update_playlist_view()
        event.stop()


def _truncate_line(text: str, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if len(text) <= max_width:
        return text
    if max_width <= 1:
        return text[:max_width]
    return text[: max_width - 1] + "…"


def run_tui(path: str, player: VlcPlayer) -> int:
    """Run the TUI and return an exit code."""
    app = RhythmSlicerApp(player=player, path=path)
    app.run()
    return 0
