"""Textual-based TUI for RhythmSlicer Pro."""

from __future__ import annotations

import importlib
import pkgutil
import asyncio
import random
from pathlib import Path
import time
from typing import Any, Callable, Iterator, Optional
import logging

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Container, Horizontal, Vertical
    from textual import events
    from textual.geometry import Region
    from textual.screen import ModalScreen
    from textual.widgets import Button, DataTable, Header, Input, Static
    from rich.text import Text
except Exception as exc:  # pragma: no cover - depends on environment
    raise RuntimeError(
        "Textual is required for the TUI. Install the 'textual' dependency."
    ) from exc

from rhythm_slicer.config import AppConfig, load_config, save_config
from rhythm_slicer.hackscript import HackFrame, generate as generate_hackscript
from rhythm_slicer.hangwatch import HangWatchdog, dump_threads
from rhythm_slicer.logging_setup import set_console_level
from rhythm_slicer.ui.frame_player import FramePlayer
from rhythm_slicer.ui.help_modal import HelpModal
from rhythm_slicer.ui.bindings import normalize_bindings
from rhythm_slicer.ui.playlist_table_manager import PlaylistTableManager
from rhythm_slicer.ui.play_order import build_play_order
from rhythm_slicer.ui.playlist_io import _load_recursive_directory
from rhythm_slicer.ui.playlist_builder import PlaylistBuilderScreen
from rhythm_slicer.ui.prompt_codec import (
    _format_open_prompt_result,
    _parse_open_prompt_result,
    _parse_prompt_result,
)
from rhythm_slicer.ui.status_controller import StatusController
from rhythm_slicer.ui.status_panel import (
    StatusPanelCache,
    StatusPanelWidgets,
    update_status_panel,
)
from rhythm_slicer.ui.textual_compat import Panel
from rhythm_slicer.ui.tui_formatters import (
    ellipsize,
    format_status_time,
    ratio_from_click,
    render_status_bar,
    status_state_label,
    target_ms_from_ratio,
    render_visualizer,
    visualizer_bars,
)
from rhythm_slicer.ui.text_helpers import _truncate_line
from rhythm_slicer.ui.visualizer_rendering import (
    center_visualizer_message,
    clip_frame_text,
    render_ansi_frame,
    render_visualizer_hud,
    render_visualizer_mode,
    render_visualizer_view,
    tiny_visualizer_text,
    visualizer_hud_size,
)
from rhythm_slicer.ui.tui_types import TrackSignature
from rhythm_slicer.ui.tui_widgets import (
    PlaylistTable,
    TransportControls,
    VisualizerHud,
)
from rhythm_slicer.visualizations.ansi import sanitize_ansi_sgr
from rhythm_slicer.metadata import (
    TrackMeta,
    get_cached_track_meta,
    get_track_meta,
)
from rhythm_slicer.player_vlc import VlcPlayer
from rhythm_slicer.playlist import (
    Playlist,
    Track,
    load_from_input,
)

logger = logging.getLogger(__name__)


# UI components
class StatusBar(Static):
    """Status bar widget."""

    def __init__(self, controller: StatusController, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._controller = controller

    def render(self) -> Text:
        width = max(1, self.size.width)
        focused = getattr(self.app, "focused", None)
        return self._controller.render_line(width, focused=focused)


# Main application
class RhythmSlicerApp(App):
    """RhythmSlicer Pro Textual application."""

    # --- App constants & metadata ---
    CSS_PATH = "app.tcss"
    TITLE = "Rhythm Slicer Pro"
    MIN_WIDTH = 41
    MIN_HEIGHT = 12
    HIDE_TRACK_WIDTH = 80
    HIDE_VISUALIZER_WIDTH = 60
    VISUALIZER_MAX_FPS = 12.0
    VISUALIZER_LOADING_STEP = 0.35

    # --- Keybindings ---
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
        Binding("[", "speed_down", "Speed -0.25x"),
        Binding("]", "speed_up", "Speed +0.25x"),
        Binding("\\", "speed_reset", "Speed 1.00x"),
        Binding("r", "cycle_repeat", "Repeat Mode"),
        Binding("h", "toggle_shuffle", "Shuffle"),
        Binding("v", "select_visualization", "Visualization"),
        Binding("ctrl+s", "save_playlist", "Save Playlist"),
        Binding("ctrl+o", "open", "Open"),
        Binding("ctrl+shift+d", "dump_threads", "Dump Threads"),
        Binding("?", "show_help", "Help"),
        Binding("f1", "show_help", "Help"),
        Binding("b", "playlist_builder", "Playlist Builder"),
        Binding("q", "quit_app", "Quit"),
    ]

    # --- Lifecycle ---
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
        self._playback_rate = 1.0
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
            Path(config.last_open_path) if config.last_open_path else None
        )
        self._open_recursive = config.open_recursive
        self._status_controller = StatusController(self._now)
        self._playing_index: Optional[int] = None
        self._visualizer: Optional[Static] = None
        self._visualizer_hud: Optional[Static] = None
        self._playlist_list: Optional[Static] = None
        self._playlist_table: Optional[PlaylistTable] = None
        self._playlist_counter: Optional[Static] = None
        self._playlist_counter_text: Optional[str] = None
        self._playlist_title_column = "title"
        self._playlist_artist_column = "artist"
        self._playlist_table_source: Optional[Playlist] = None
        self._playlist_table_width = 0
        self._playlist_title_max = 0
        self._playlist_artist_max = 0
        self._playing_key: Optional[str] = None
        self._selected_key: Optional[str] = None
        self._missing_row_keys_logged: set[str] = set()
        self._user_navigating_until = 0.0
        self._track_panel_last_update = 0.0
        self._track_panel_last_signature: Optional[TrackSignature] = None
        self._track_panel_last_track_key: Optional[str] = None
        self._loading = False
        self._play_request_id = 0
        self._status_time_bar: Optional[Static] = None
        self._status_time_text: Optional[Static] = None
        self._status_volume_bar: Optional[Static] = None
        self._status_volume_text: Optional[Static] = None
        self._status_speed_bar: Optional[Static] = None
        self._status_speed_text: Optional[Static] = None
        self._status_state_text: Optional[Static] = None
        self._ui_tick_count = 0
        self._volume_scrub_active = False
        self._speed_scrub_active = False
        self._status_panel_cache = StatusPanelCache(
            last_time_text=None,
            last_time_value=None,
            last_time_bar_text=None,
            last_volume_text=None,
            last_volume_value=None,
            last_volume_bar_text=None,
            last_speed_text=None,
            last_speed_value=None,
            last_speed_bar_text=None,
            last_state_text=None,
            last_message_level=None,
        )
        self._frame_player = FramePlayer(self)
        self._current_track_path: Optional[Path] = None
        self._viewport_width = 1
        self._viewport_height = 1
        self._last_visualizer_text: Optional[str] = None
        self._last_visualizer_key: Optional[object] = None
        self._last_visualizer_update = 0.0
        self._viz_prefs: dict[str, object] = {}
        self._viz_restart_timer: Optional[object] = None
        self._visualizer_ready = False
        self._visualizer_init_attempts = 0
        self._last_ui_tick = self._now()
        self._hang_watchdog: Optional[HangWatchdog] = None
        self._too_small_active = False
        self._suppress_table_events = False
        self._meta_loading: set[Path] = set()
        self._viz_request_id = 0
        self._playlist_table_manager = PlaylistTableManager(self)

    # --- Widget composition & layout ---
    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Container(id="root"):
            yield Static(
                "Terminal too small (min 41x12)",
                id="too_small",
            )
            with Horizontal(id="body"):
                with Panel(title="Playlist", id="playlist_panel"):
                    with Vertical(id="playlist_stack"):
                        yield PlaylistTable(id="playlist_table")
                        with Horizontal(id="playlist_controls"):
                            yield Static("0000/0000", id="playlist_counter")
                            yield Button(
                                "R:OFF", id="repeat_toggle", classes="playlist_toggle"
                            )
                            yield Button(
                                "S:OFF", id="shuffle_toggle", classes="playlist_toggle"
                            )
                        yield TransportControls()
                        with Container(id="legacy_controls"):
                            yield Static(id="playlist_list", markup=True)
                            with Horizontal(id="playlist_footer"):
                                yield Static(id="playlist_footer_track")
                            yield Horizontal(
                                Button(
                                    Text("[<<]"), id="key_prev", classes="transport_key"
                                ),
                                Button(
                                    Text("[ PLAY ] "),
                                    id="key_playpause",
                                    classes="transport_key",
                                ),
                                Button(
                                    Text("[ STOP ]"),
                                    id="key_stop",
                                    classes="transport_key",
                                ),
                                Button(
                                    Text("[>>]"), id="key_next", classes="transport_key"
                                ),
                                id="transport_row",
                            )
                with Vertical(id="right_column"):
                    with Panel(title="Visualizer", id="visualizer_panel"):
                        yield Static(id="visualizer")
                    with Panel(title="Current Track", id="track_panel"):
                        yield VisualizerHud(id="visualizer_hud")
            with Panel(title="Status", id="status_panel"):
                with Vertical(id="status_stack"):
                    with Horizontal(id="status_time_row"):
                        yield Static("TIME:", id="status_time_label", markup=False)
                        yield Static("", id="status_time_bar", markup=False)
                        yield Static(
                            "--:-- / --:--", id="status_time_text", markup=False
                        )
                    with Horizontal(id="status_volume_row"):
                        yield Static("VOL:", id="status_volume_label", markup=False)
                        yield Static("", id="status_volume_bar", markup=False)
                        yield Static("  0", id="status_volume_text", markup=False)
                        yield Static("SPD:", id="status_speed_label", markup=False)
                        yield Static("", id="status_speed_bar", markup=False)
                        yield Static("1.00x", id="status_speed_text", markup=False)
                        yield Static(
                            "[ STOPPED ]", id="status_state_text", markup=False
                        )

    # --- Internal helpers ---
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
            self._refresh_visualizer(force=True)
        self._visualizer_ready = True
        logger.info(
            "Visualizer layout ready (%sx%s)",
            self._viewport_width,
            self._viewport_height,
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
        self._update_status_panel(force=True)

    def _save_config(self) -> None:
        self._config = AppConfig(
            last_open_path=str(self._last_open_path) if self._last_open_path else None,
            open_recursive=self._open_recursive,
            volume=self._volume,
            repeat_mode=self._repeat_mode,
            shuffle=self._shuffle,
            viz_name=self._viz_name,
            ansi_colors=self._ansi_colors,
        )
        save_config(self._config)

    def _status_state_label(self) -> str:
        return status_state_label(
            playback_state_label=self._playback_state_label,
            shuffle=self._shuffle,
            repeat_mode=self._repeat_mode,
        )

    def _playback_state_label(self) -> str:
        if self._loading:
            return "LOADING"
        state = (self.player.get_state() or "").lower()
        if "playing" in state:
            return "PLAYING"
        if "paused" in state:
            return "PAUSED"
        if "stop" in state:
            return "STOPPED"
        return "STOPPED"

    def _visualizer_mode(self) -> str:
        if self._loading:
            return "LOADING"
        if not self.playlist or self.playlist.is_empty():
            return "IDLE"
        return self._playback_state_label()

    def _format_status_time(self) -> tuple[str, int]:
        return format_status_time(
            loading=self._loading,
            get_position_ms=self.player.get_position_ms,
            get_length_ms=self.player.get_length_ms,
        )

    def _bar_widget_width(self, widget: Static) -> int:
        size = getattr(widget, "content_size", None) or widget.size
        return max(1, getattr(size, "width", 1))

    # --- Rendering helpers ---
    def _render_status_bar(self, width: int, ratio: float) -> str:
        return render_status_bar(width, ratio)

    # --- Playlist + transport ---
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

    def _render_header(self) -> str:
        return "<< Rhythm Slicer Pro >>"

    # --- Visualizer ---
    def _render_visualizer(self) -> str:
        width, height = self._visualizer_viewport()
        if width <= 0 or height <= 0 or width <= 2 or height <= 1:
            return render_visualizer_view(
                width=width,
                height=height,
                mode="",
                frame_player_is_running=self._frame_player.is_running,
                seed_ms=0,
                bars_fn=visualizer_bars,
                render_bars_fn=render_visualizer,
                render_mode_fn=self._render_visualizer_mode,
                tiny_text_fn=self._tiny_visualizer_text,
            )
        mode = self._visualizer_mode()
        seed_ms = 0
        if mode == "PLAYING" and not self._frame_player.is_running:
            seed_ms = self._get_playback_position_ms() or int(self._now() * 1000)
        return render_visualizer_view(
            width=width,
            height=height,
            mode=mode,
            frame_player_is_running=self._frame_player.is_running,
            seed_ms=seed_ms,
            bars_fn=visualizer_bars,
            render_bars_fn=render_visualizer,
            render_mode_fn=self._render_visualizer_mode,
            tiny_text_fn=self._tiny_visualizer_text,
        )

    def _render_visualizer_mode(self, mode: str, width: int, height: int) -> str:
        return render_visualizer_mode(
            mode,
            width,
            height,
            now=self._now,
            loading_step=self.VISUALIZER_LOADING_STEP,
            tiny_text_fn=self._tiny_visualizer_text,
            center_message_fn=self._center_visualizer_message,
        )

    def _render_visualizer_hud(self) -> Text:
        width, height = self._visualizer_hud_size()
        return render_visualizer_hud(
            width=width,
            height=height,
            playlist=self.playlist,
            playing_index=self._playing_index,
            get_meta_cached=self._get_track_meta_cached,
            ensure_meta_loaded=self._ensure_track_meta_loaded,
            ellipsize_fn=ellipsize,
        )

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

    def _render_track_counter(self) -> str:
        total_tracks = len(self.playlist.tracks) if self.playlist else 0
        width = max(4, len(str(total_tracks)))
        playing_index = self._playing_index
        display_index = playing_index + 1 if playing_index is not None else 0
        return f"{display_index:0{width}d}/{total_tracks:0{width}d}"

    def _render_playlist_footer(self) -> str:
        if not self.playlist or self.playlist.is_empty():
            current = "--"
            total = 0
        else:
            current = str(self.playlist.index + 1)
            total = len(self.playlist.tracks)
        text = f"Track: {current}/{total}"
        return _truncate_line(text, self._playlist_width())

    def _render_ansi_frame(self, text: str, width: int, height: int) -> Text:
        return render_ansi_frame(text, width, height)

    def _update_status_panel(self, *, force: bool = False) -> None:
        if (
            not self._status_time_bar
            or not self._status_time_text
            or not self._status_volume_bar
            or not self._status_volume_text
            or not self._status_speed_bar
            or not self._status_speed_text
            or not self._status_state_text
        ):
            return
        widgets = StatusPanelWidgets(
            time_bar=self._status_time_bar,
            time_text=self._status_time_text,
            volume_bar=self._status_volume_bar,
            volume_text=self._status_volume_text,
            speed_bar=self._status_speed_bar,
            speed_text=self._status_speed_text,
            state_text=self._status_state_text,
        )
        update_status_panel(
            widgets=widgets,
            cache=self._status_panel_cache,
            force=force,
            format_status_time=self._format_status_time,
            volume=self._volume,
            playback_rate=self._playback_rate,
            bar_widget_width=self._bar_widget_width,
            render_status_bar=self._render_status_bar,
            status_state_label=self._status_state_label,
            current_message=self._status_controller._current_message,
        )

    # --- Playlist + transport ---

    def _update_transport_row(self) -> None:
        try:
            label = self.query_one("#key_playpause", Button)
        except Exception:
            return
        label.label = self._render_transport_label()

    def _refresh_transport_controls(self) -> None:
        try:
            controls = self.query_one(TransportControls)
        except Exception:
            return
        controls.refresh_state()

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
        self._ui_tick_count += 1
        self._update_screen_title()
        self._refresh_visualizer()
        self._update_transport_row()
        if self._ui_tick_count == 1:
            self._update_playlist_view()
        if self.player.consume_end_reached():
            self._advance_track(auto=True)

    def _update_screen_title(self) -> None:
        self.title = "Rhythm Slicer Pro"

    # --- Visualizer ---

    def _get_track_meta_cached(self, path: Path) -> Optional[TrackMeta]:
        return get_cached_track_meta(path)

    def _ensure_track_meta_loaded(self, path: Path) -> None:
        if get_cached_track_meta(path) is not None:
            return
        if path in self._meta_loading:
            return
        self._meta_loading.add(path)

        async def load_meta() -> None:
            try:
                await asyncio.to_thread(get_track_meta, path)
            except Exception:
                logger.exception("Metadata load failed for %s", path)
            finally:
                self._meta_loading.discard(path)
            self._update_playlist_view()
            self._update_visualizer_hud()

        self.run_worker(load_meta(), exclusive=False)

    def _center_visualizer_message(self, message: str, width: int, height: int) -> str:
        return center_visualizer_message(message, width, height)

    def _visualizer_hud_size(self) -> tuple[int, int]:
        return visualizer_hud_size(self._visualizer_hud)

    def _current_track_signature(self) -> TrackSignature:
        track_key = (
            self._playlist_row_key(self._playing_index)
            if self._playing_index is not None
            else None
        )
        track = None
        if self.playlist and self._playing_index is not None:
            if 0 <= self._playing_index < len(self.playlist.tracks):
                track = self.playlist.tracks[self._playing_index]
        meta = self._get_track_meta_cached(track.path) if track else None
        if track and meta is None:
            self._ensure_track_meta_loaded(track.path)
        title = meta.title if meta and meta.title else (track.title if track else "—")
        if not title and track:
            title = track.path.name
        artist = meta.artist if meta and meta.artist else "Unknown"
        album = meta.album if meta and meta.album else "Unknown"
        width, height = self._visualizer_hud_size()
        return (
            track_key,
            title,
            artist,
            album,
            width,
            height,
        )

    def _update_visualizer_hud(self) -> None:
        if not self._visualizer_hud:
            return
        signature = self._current_track_signature()
        track_key = signature[0]
        now = self._now()
        if signature == self._track_panel_last_signature:
            return
        if (
            track_key == self._track_panel_last_track_key
            and now - self._track_panel_last_update < 0.25
        ):
            return
        self._visualizer_hud.update(self._render_visualizer_hud())
        self._track_panel_last_update = now
        self._track_panel_last_signature = signature
        self._track_panel_last_track_key = track_key

    # --- Playlist table (sizing + refresh) ---
    def _init_playlist_table(self) -> None:
        self._playlist_table_manager._init_playlist_table()

    def _refresh_playlist_table_after_layout(self) -> None:
        self._playlist_table_manager._refresh_playlist_table_after_layout()

    def _playlist_row_key(self, index: int) -> str:
        return self._playlist_table_manager._playlist_row_key(index)

    def _playlist_table_content_width(self) -> int:
        return self._playlist_table_manager._playlist_table_content_width()

    def _playlist_table_limits(self) -> tuple[int, int, int]:
        return self._playlist_table_manager._playlist_table_limits()

    def _playlist_row_cells(
        self,
        track: Track,
        *,
        is_playing: bool,
        title_max: int,
        artist_max: int,
    ) -> tuple[Text, Text]:
        return self._playlist_table_manager._playlist_row_cells(
            track,
            is_playing=is_playing,
            title_max=title_max,
            artist_max=artist_max,
        )

    def _move_table_cursor(self, row_index: int) -> None:
        self._playlist_table_manager._move_table_cursor(row_index)

    def _restore_table_cursor_from_selected(self) -> None:
        self._playlist_table_manager._restore_table_cursor_from_selected()

    def _refresh_playlist_table(self, *, rebuild: bool = False) -> None:
        self._playlist_table_manager._refresh_playlist_table(rebuild=rebuild)

    def _update_playing_row_style(self) -> None:
        self._playlist_table_manager._update_playing_row_style()

    def _update_row_cells(
        self,
        row_key: str,
        title_cell: Text,
        artist_cell: Text,
    ) -> bool:
        return self._playlist_table_manager._update_row_cells(
            row_key,
            title_cell,
            artist_cell,
        )

    def _set_selected(
        self,
        index: int,
        *,
        move_cursor: bool = True,
        update_selected_key: bool = True,
    ) -> None:
        self._playlist_table_manager._set_selected(
            index,
            move_cursor=move_cursor,
            update_selected_key=update_selected_key,
        )

    def _set_user_navigation_lockout(self) -> None:
        self._user_navigating_until = time.monotonic() + 1.0

    async def _populate_playlist(self) -> None:
        if self.playlist is None:
            return
        self._update_playlist_view()

    def _sync_selection(self) -> None:
        if not self.playlist or self.playlist.is_empty():
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
        self._refresh_transport_controls()

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
        self._play_current_track(on_failure="skip")
        self._refresh_transport_controls()

    def _set_loading(self, active: bool, *, message: str = "Loading...") -> None:
        self._loading = active
        if active:
            self._set_message(message, timeout=0.0)
        self._refresh_visualizer(force=True)
        self._refresh_transport_controls()
        self._update_status_panel(force=True)

    def _load_and_play_blocking(self, track: Track) -> None:
        self.player.load(str(track.path))
        self.player.play()
        setter = getattr(self.player, "set_playback_rate", None)
        if callable(setter):
            setter(self._playback_rate)

    async def _play_track_worker(
        self,
        track: Track,
        *,
        request_id: int,
        on_failure: str,
    ) -> None:
        try:
            await asyncio.to_thread(self._load_and_play_blocking, track)
        except Exception as exc:
            self._handle_playback_error(exc, track, on_failure, request_id)
        else:
            self._handle_playback_started(track, request_id)

    def _handle_playback_started(self, track: Track, request_id: Optional[int]) -> None:
        if request_id is not None and request_id != self._play_request_id:
            return
        self._loading = False
        playlist_index = self.playlist.index if self.playlist else None
        self._playing_index = playlist_index
        logger.info("Track change index=%s path=%s", playlist_index, track.path)
        self._set_message("Playing")
        self._update_playing_row_style()
        self._sync_selection()
        self._start_hackscript(
            track.path,
            playback_pos_ms=self._get_playback_position_ms(),
            playback_state=self._get_playback_state(),
        )
        self._update_visualizer_hud()
        self._update_playlist_controls()
        self._refresh_transport_controls()
        self._update_status_panel(force=True)

    def _handle_playback_error(
        self,
        exc: Exception,
        track: Track,
        on_failure: str,
        request_id: Optional[int],
    ) -> None:
        if request_id is not None and request_id != self._play_request_id:
            return
        self._loading = False
        logger.exception("Playback failed for %s", track.path)
        self._set_message(f"Failed to play: {track.title}", level="error")
        self._refresh_transport_controls()
        if on_failure == "skip":
            self._skip_failed_track()
        self._update_status_panel(force=True)

    def _play_current_track(self, *, on_failure: str = "message") -> bool:
        if not self.playlist or self.playlist.is_empty():
            return False
        track = self.playlist.current()
        if not track:
            return False
        self._play_request_id += 1
        request_id = self._play_request_id
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            try:
                self._load_and_play_blocking(track)
            except Exception as exc:
                self._handle_playback_error(exc, track, on_failure, request_id)
                return False
            self._handle_playback_started(track, request_id)
            return True
        self._set_loading(True)
        self.run_worker(
            self._play_track_worker(
                track, request_id=request_id, on_failure=on_failure
            ),
            exclusive=True,
        )
        return True

    def _advance_track(self, auto: bool = False) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        if auto and self._repeat_mode == "one":
            self._play_current_track(on_failure="skip")
            return
        wrap = self._repeat_mode == "all"
        next_index = self._next_index(wrap=wrap)
        if next_index is None:
            if auto and self._repeat_mode == "off":
                self.player.stop()
                self._stop_hackscript()
            self._set_message("End of playlist")
            return
        self._set_selected(next_index, move_cursor=False, update_selected_key=False)
        self._play_current_track(on_failure="skip")

    def _skip_failed_track(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        attempts = len(self.playlist.tracks)
        while attempts > 0:
            track = self.playlist.next()
            if track is None:
                break
            if self._play_current_track(on_failure="skip"):
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

    # --- Actions (Textual) ---
    def action_toggle_playback(self) -> None:
        state = (self.player.get_state() or "").lower()
        if "playing" in state:
            self.player.pause()
            self._set_message("Paused")
            desired_state = "paused"
            logger.info("Playback paused")
        elif "paused" in state:
            self.player.play()
            setter = getattr(self.player, "set_playback_rate", None)
            if callable(setter):
                setter(self._playback_rate)
            self._set_message("Playing")
            desired_state = "playing"
            logger.info("Playback resumed")
        else:
            if self.playlist and not self.playlist.is_empty():
                if self._play_current_track(on_failure="message"):
                    logger.info("Playback started")
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
        self._refresh_transport_controls()
        self._update_status_panel(force=True)

    def action_stop(self) -> None:
        if self._loading:
            self._play_request_id += 1
            self._loading = False
        self.player.stop()
        self._playing_index = None
        self._stop_hackscript()
        self._set_message("Stopped")
        logger.info("Playback stopped")
        self._update_visualizer_hud()
        self._refresh_playlist_table()
        self._update_playlist_controls()
        self._refresh_transport_controls()
        self._update_status_panel(force=True)

    def action_seek_back(self) -> None:
        if self._try_seek(-5000):
            self._schedule_viz_restart()

    def action_seek_forward(self) -> None:
        if self._try_seek(5000):
            self._schedule_viz_restart()

    def action_volume_up(self) -> None:
        self._volume = min(100, self._volume + 5)
        self.player.set_volume(self._volume)
        self._set_message("Volume up")
        self._save_config()
        self._update_status_panel(force=True)

    def action_volume_down(self) -> None:
        self._volume = max(0, self._volume - 5)
        self.player.set_volume(self._volume)
        self._set_message("Volume down")
        self._save_config()
        self._update_status_panel(force=True)

    def action_speed_down(self) -> None:
        self._apply_playback_rate(self._playback_rate - 0.25, message="Speed")

    def action_speed_up(self) -> None:
        self._apply_playback_rate(self._playback_rate + 0.25, message="Speed")

    def action_speed_reset(self) -> None:
        self._apply_playback_rate(1.0, message="Speed reset")

    def action_next_track(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            self._refresh_transport_controls()
            return
        next_index = self._next_index(wrap=self._repeat_mode == "all")
        if next_index is None:
            self._set_message("End of playlist")
            self._refresh_transport_controls()
            return
        self._set_selected(next_index)
        self._play_current_track(on_failure="skip")
        self._refresh_transport_controls()

    def action_previous_track(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            self._refresh_transport_controls()
            return
        prev_index = self._prev_index(wrap=self._repeat_mode == "all")
        if prev_index is None:
            self._set_message("Start of playlist")
            self._refresh_transport_controls()
            return
        self._set_selected(prev_index)
        self._play_current_track(on_failure="skip")
        self._refresh_transport_controls()

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
        self.push_screen(HelpModal(self._help_bindings()))

    def action_playlist_builder(self) -> None:
        start_path = None
        if self._current_track_path and self._current_track_path.exists():
            start_path = self._current_track_path.parent
        elif self._last_open_path and self._last_open_path.exists():
            start_path = (
                self._last_open_path
                if self._last_open_path.is_dir()
                else self._last_open_path.parent
            )
        else:
            start_path = Path.cwd()
        self.push_screen(PlaylistBuilderScreen(start_path))

    def action_move_up(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_user_navigation_lockout()
        self._set_selected(max(0, self.playlist.index - 1))

    def action_move_down(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_user_navigation_lockout()
        self._set_selected(min(len(self.playlist.tracks) - 1, self.playlist.index + 1))

    def action_play_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            self._refresh_transport_controls()
            return
        try:
            focused = self.focused
        except Exception:
            focused = self._playlist_list
        if (
            focused is not None
            and focused is not self._playlist_list
            and focused is not self._playlist_table
        ):
            return
        self._play_selected()
        self._refresh_transport_controls()

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
            self._playing_index
            if self._playing_index is not None
            else self.playlist.index
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
                self._refresh_transport_controls()
            else:
                self._set_message(f"Removed: {removed_track.title}")
            return
        self._update_playlist_view()
        if was_playing:
            self._play_current_track(on_failure="skip")
        self._set_message(f"Removed: {removed_track.title}")
        self._refresh_transport_controls()

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
        self.run_worker(self._select_visualization_flow(), exclusive=True)

    async def action_save_playlist(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks to save", level="warn")
            return
        self.run_worker(self._save_playlist_flow(), exclusive=True)

    async def action_load_playlist(self) -> None:
        self.run_worker(self._load_playlist_flow(), exclusive=True)

    async def action_open(self) -> None:
        self.run_worker(self._open_flow(), exclusive=True)

    def _help_bindings(self) -> list[Binding]:
        return normalize_bindings(self.BINDINGS)

    # --- Event handlers ---
    async def on_mount(self) -> None:
        self._update_screen_title()
        self._visualizer = self.query_one("#visualizer", Static)
        self._visualizer_hud = self.query_one("#visualizer_hud", Static)
        self._playlist_list = self.query_one("#playlist_list", Static)
        self._playlist_table = self.query_one("#playlist_table", PlaylistTable)
        self._playlist_counter = self.query_one("#playlist_counter", Static)
        self._playlist_list.can_focus = True
        self._status_time_bar = self.query_one("#status_time_bar", Static)
        self._status_time_text = self.query_one("#status_time_text", Static)
        self._status_volume_bar = self.query_one("#status_volume_bar", Static)
        self._status_volume_text = self.query_one("#status_volume_text", Static)
        self._status_speed_bar = self.query_one("#status_speed_bar", Static)
        self._status_speed_text = self.query_one("#status_speed_text", Static)
        self._status_state_text = self.query_one("#status_state_text", Static)
        self._init_playlist_table()
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
            self._play_current_track(on_failure="skip")
        else:
            self._set_message("No tracks loaded")
        if self._playlist_table:
            self.set_focus(self._playlist_table)
        self._update_transport_row()
        self.set_interval(0.1, self._on_tick)
        self.set_interval(0.25, self._update_status_panel)
        self.set_interval(0.5, self._update_ui_tick)
        self.set_interval(10.0, self._log_heartbeat)
        self.call_later(self._finalize_visualizer_layout)
        # Ensure the playlist table sizes itself once layout measurements are available.
        self.set_timer(0.05, self._refresh_playlist_table_after_layout)
        self._apply_layout_constraints()
        self._update_status_panel(force=True)
        logger.info("TUI mounted")

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

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if self._suppress_table_events:
            return
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_user_navigation_lockout()
        raw_key = getattr(event.row_key, "value", None)
        if raw_key is None:
            return
        try:
            index = int(raw_key)
        except (TypeError, ValueError):
            return
        self._selected_key = raw_key
        if index == self.playlist.index:
            return
        self._set_selected(index, move_cursor=False, update_selected_key=True)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if not self.playlist or self.playlist.is_empty():
            return
        self._set_user_navigation_lockout()
        raw_key = getattr(event.row_key, "value", None)
        if raw_key is not None:
            try:
                index = int(raw_key)
            except (TypeError, ValueError):
                index = self.playlist.index
            else:
                self._selected_key = raw_key
                if index != self.playlist.index:
                    self._set_selected(
                        index, move_cursor=False, update_selected_key=True
                    )
        self.action_play_selected()

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        del event
        self._set_user_navigation_lockout()

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if self._status_time_bar and getattr(self._status_time_bar, "region", None):
            time_region = self._status_time_bar.region
            sx = getattr(event, "screen_x", event.x)
            sy = getattr(event, "screen_y", event.y)
            if time_region.contains(sx, sy):
                ratio = ratio_from_click(int(sx - time_region.x), time_region.width)
                self._seek_to_ratio(ratio)
                self._scrub_active = True
                event.stop()
                return
        if self._status_volume_bar and getattr(self._status_volume_bar, "region", None):
            volume_region = self._status_volume_bar.region
            sx = getattr(event, "screen_x", event.x)
            sy = getattr(event, "screen_y", event.y)
            if volume_region.contains(sx, sy):
                ratio = ratio_from_click(int(sx - volume_region.x), volume_region.width)
                self._set_volume_from_ratio(ratio)
                self._volume_scrub_active = True
                event.stop()
                return
        if self._status_speed_bar and getattr(self._status_speed_bar, "region", None):
            speed_region = self._status_speed_bar.region
            sx = getattr(event, "screen_x", event.x)
            sy = getattr(event, "screen_y", event.y)
            if speed_region.contains(sx, sy):
                ratio = ratio_from_click(int(sx - speed_region.x), speed_region.width)
                self._set_speed_from_ratio(ratio)
                self._speed_scrub_active = True
                event.stop()
                return
        if self._playlist_table and getattr(self._playlist_table, "region", None):
            table_region = self._playlist_table.region
            sx = getattr(event, "screen_x", event.x)
            sy = getattr(event, "screen_y", event.y)
            if table_region.contains(sx, sy):
                return
        if not self._playlist_list:
            return
        region: Optional[Region] = getattr(self._playlist_list, "region", None)
        sx = getattr(event, "screen_x", event.x)
        sy = getattr(event, "screen_y", event.y)
        if region and not region.contains(sx, sy):
            return
        row = int(sy - region.y) if region else int(getattr(event, "offset_y", event.y))
        index = self._row_to_index(row)
        if index is None:
            return
        self.set_focus(self._playlist_list)
        now = self._now()
        if self._last_click_index == index and now - self._last_click_time <= 0.4:
            self._set_selected(index)
            self._play_selected()
        else:
            self._set_selected(index)
        self._last_click_index = index
        self._last_click_time = now

    def on_mouse_move(self, event: events.MouseMove) -> None:
        sx = getattr(event, "screen_x", event.x)
        sy = getattr(event, "screen_y", event.y)
        if self._scrub_active and self._status_time_bar:
            region = getattr(self._status_time_bar, "region", None)
            if region and region.contains(sx, sy):
                ratio = ratio_from_click(int(sx - region.x), region.width)
                self._seek_to_ratio(ratio)
                event.stop()
            return
        if self._volume_scrub_active and self._status_volume_bar:
            region = getattr(self._status_volume_bar, "region", None)
            if region and region.contains(sx, sy):
                ratio = ratio_from_click(int(sx - region.x), region.width)
                self._set_volume_from_ratio(ratio)
                event.stop()
        if self._speed_scrub_active and self._status_speed_bar:
            region = getattr(self._status_speed_bar, "region", None)
            if region and region.contains(sx, sy):
                ratio = ratio_from_click(int(sx - region.x), region.width)
                self._set_speed_from_ratio(ratio)
                event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        if self._scrub_active:
            self._scrub_active = False
            event.stop()
            return
        if self._volume_scrub_active:
            self._volume_scrub_active = False
            self._save_config()
            event.stop()
            return
        if self._speed_scrub_active:
            self._speed_scrub_active = False
            event.stop()
            return
        del event

    def on_resize(self, event: events.Resize) -> None:
        del event
        self._apply_layout_constraints()
        if self._too_small_active:
            return
        self._update_visualizer_viewport()
        self._update_playlist_view()
        self._update_visualizer_hud()
        self._update_status_panel(force=True)
        self.set_timer(0.05, self._refresh_playlist_table_after_layout)
        if self._current_track_path:
            self._schedule_viz_restart(0.1)
        elif self._visualizer and not self._frame_player.is_running:
            self._refresh_visualizer(force=True)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if not self._playlist_list:
            return
        if self._playlist_table and getattr(self._playlist_table, "region", None):
            table_region = self._playlist_table.region
            sx = getattr(event, "screen_x", event.x)
            sy = getattr(event, "screen_y", event.y)
            if table_region.contains(sx, sy):
                return
        region: Optional[Region] = getattr(self._playlist_list, "region", None)
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
        if self._playlist_table and getattr(self._playlist_table, "region", None):
            table_region = self._playlist_table.region
            sx = getattr(event, "screen_x", event.x)
            sy = getattr(event, "screen_y", event.y)
            if table_region.contains(sx, sy):
                return
        region: Optional[Region] = getattr(self._playlist_list, "region", None)
        sx = getattr(event, "screen_x", event.x)
        sy = getattr(event, "screen_y", event.y)
        if region and not region.contains(sx, sy):
            return
        self._scroll_offset = max(0, self._scroll_offset - 1)
        self._update_playlist_view()
        event.stop()

    async def _select_visualization_flow(self) -> None:
        choices = self._list_visualizations()
        result = await self.push_screen_wait(VizPrompt(self._viz_name, choices))
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

    def _update_playlist_view(self) -> None:
        if not self._playlist_list or not self.playlist:
            self._refresh_playlist_table()
            self._update_playlist_controls()
            return
        width = self._playlist_width()
        view_height = self._playlist_view_height()
        if self.playlist.is_empty():
            message = _truncate_line("No tracks loaded", width)
            self._playlist_list.update(message)
            self._update_playlist_controls()
            self._refresh_playlist_table()
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
        self._update_playlist_controls()
        self._refresh_playlist_table()

    def _update_playlist_controls(self) -> None:
        if not self._playlist_counter:
            return
        counter_text = self._render_track_counter()
        if counter_text != self._playlist_counter_text:
            self._playlist_counter.update(counter_text)
            self._playlist_counter_text = counter_text
        try:
            repeat = self.query_one("#repeat_toggle", Button)
            shuffle = self.query_one("#shuffle_toggle", Button)
        except Exception:
            return
        repeat.label = self._render_repeat_label()
        shuffle.label = self._render_shuffle_label()
        if self._playlist_list:
            try:
                track = self.query_one("#playlist_footer_track", Static)
            except Exception:
                return
            track.update(self._render_playlist_footer())

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

    def _play_selected(self) -> None:
        if not self.playlist or self.playlist.is_empty():
            self._set_message("No tracks loaded")
            return
        self._sync_play_order_pos()
        self._play_current_track(on_failure="skip")
        self._sync_selection()

    def _set_volume_from_ratio(self, ratio: float) -> None:
        volume = int(max(0.0, min(1.0, ratio)) * 100)
        if volume == self._volume:
            return
        self._volume = volume
        self.player.set_volume(self._volume)
        self._update_status_panel(force=True)

    def _set_speed_from_ratio(self, ratio: float) -> None:
        rate = 0.5 + (max(0.0, min(1.0, ratio)) * (4.0 - 0.5))
        self._apply_playback_rate(rate, message="Speed")

    def _clamp_snap_rate(self, rate: float) -> float:
        min_rate = 0.5
        max_rate = 4.0
        step = 0.25
        try:
            rate_value = float(rate)
        except (TypeError, ValueError):
            rate_value = 1.0
        steps = round((rate_value - min_rate) / step)
        snapped = min_rate + (steps * step)
        return round(max(min_rate, min(max_rate, snapped)), 2)

    def _apply_playback_rate(self, rate: float, *, message: str) -> None:
        snapped = self._clamp_snap_rate(rate)
        self._playback_rate = snapped
        setter = getattr(self.player, "set_playback_rate", None)
        if callable(setter):
            setter(snapped)
        self._update_status_panel(force=True)
        self._set_message(f"{message} {snapped:0.2f}x")
        self._restart_hackscript_from_player()

    def _apply_layout_constraints(self) -> None:
        width = max(0, self.size.width)
        height = max(0, self.size.height)
        too_small = width < self.MIN_WIDTH or height < self.MIN_HEIGHT
        self._too_small_active = too_small
        body = self.query_one("#body", Horizontal)
        status_panel = self.query_one("#status_panel", Panel)
        too_small_widget = self.query_one("#too_small", Static)
        body.styles.display = "none" if too_small else "block"
        status_panel.styles.display = "none" if too_small else "block"
        too_small_widget.styles.display = "block" if too_small else "none"
        if too_small:
            return
        show_track = width >= self.HIDE_TRACK_WIDTH
        show_visualizer = width >= self.HIDE_VISUALIZER_WIDTH
        track_panel = self.query_one("#track_panel", Panel)
        visualizer_panel = self.query_one("#visualizer_panel", Panel)
        right_column = self.query_one("#right_column", Vertical)
        track_panel.styles.display = "block" if show_track else "none"
        visualizer_panel.styles.display = "block" if show_visualizer else "none"
        right_column.styles.display = "block" if show_visualizer else "none"

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
        if self.playlist:
            current = self.playlist.current()
            if current:
                return current.path.parent / "playlist.m3u8"
        return Path.cwd() / "playlist.m3u8"

    async def _save_playlist_flow(self) -> None:
        playlist = self.playlist
        if playlist is None:
            self._set_message("Playlist is empty", level="warn")
            return
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

            save_m3u8(playlist, dest, mode="absolute" if absolute else "auto")
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
        preserve_track = self.playlist.current() if self.playlist else None
        preserve = preserve_track.path if preserve_track else None
        await self.set_playlist(new_playlist, preserve_path=preserve)
        self._last_playlist_path = path
        if self._play_current_track(on_failure="skip"):
            self._set_message(f"Loaded playlist: {path}")
            logger.info("Playlist loaded from %s", path)

    async def _open_flow(self) -> None:
        default = str(self._last_open_path) if self._last_open_path else ""
        result = await self.push_screen_wait(OpenPrompt(default, self._open_recursive))
        if not result:
            return
        path_str, recursive = _parse_open_prompt_result(result)
        await self._handle_open_path(path_str, recursive=recursive)

    async def _handle_open_path(
        self, path_str: str, *, recursive: bool = False
    ) -> None:
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
        return tiny_visualizer_text(width, height)

    def _clip_frame_text(self, text: str, width: int, height: int) -> str:
        return clip_frame_text(text, width, height)

    def _show_frame(self, frame: HackFrame) -> None:
        if not self._visualizer:
            return
        if self._visualizer_mode() not in {"PLAYING", "PAUSED"}:
            return
        now = self._now()
        if now - self._last_visualizer_update < (1.0 / self.VISUALIZER_MAX_FPS):
            return
        width, height = self._visualizer_viewport()
        if width <= 2 or height <= 1:
            text = self._tiny_visualizer_text(width, height)
            self._update_visualizer_content(text, ("tiny", width, height, text))
            return
        use_ansi = bool(self._viz_prefs.get("ansi_colors", False))
        if use_ansi:
            sanitized = sanitize_ansi_sgr(frame.text)
            rendered = self._render_ansi_frame(sanitized, width, height)
            key = ("ansi", width, height, sanitized)
            self._update_visualizer_content(rendered, key)
        else:
            clipped = self._clip_frame_text(frame.text, width, height)
            key = ("plain", width, height, clipped)
            self._update_visualizer_content(clipped, key)

    def _update_visualizer_content(self, content: Text | str, key: object) -> None:
        if not self._visualizer:
            return
        if key == self._last_visualizer_key:
            return
        self._last_visualizer_key = key
        if isinstance(content, Text):
            self._last_visualizer_text = content.plain
        else:
            self._last_visualizer_text = content
        self._visualizer.update(content)
        self._last_visualizer_update = self._now()

    def _refresh_visualizer(self, *, force: bool = False) -> None:
        if not self._visualizer:
            return
        width, height = self._visualizer_viewport()
        if width <= 0 or height <= 0:
            return
        mode = self._visualizer_mode()
        if width <= 2 or height <= 1:
            text = self._tiny_visualizer_text(width, height)
            self._update_visualizer_content(text, ("tiny", width, height, text))
            return
        if mode == "PLAYING":
            if self._frame_player.is_running:
                return
            text = self._render_visualizer()
            key = ("playing", width, height, text)
            if force:
                self._last_visualizer_key = None
            self._update_visualizer_content(text, key)
            return
        if mode == "PAUSED":
            if self._frame_player.is_running:
                return
            text = self._render_visualizer_mode(mode, width, height)
            key = (mode, width, height, text)
            if force:
                self._last_visualizer_key = None
            self._update_visualizer_content(text, key)
            return
        text = self._render_visualizer_mode(mode, width, height)
        key = (mode, width, height, text)
        if force:
            self._last_visualizer_key = None
        self._update_visualizer_content(text, key)

    def _prepare_hackscript_frames(
        self,
        track_path: Path,
        viewport: tuple[int, int],
        prefs: dict[str, object],
    ) -> tuple[Optional[Iterator[HackFrame]], Optional[HackFrame]]:
        frames = generate_hackscript(
            track_path,
            viewport,
            prefs,
            viz_name=self._viz_name,
        )
        try:
            first_frame = next(frames)
        except StopIteration:
            return None, None
        return frames, first_frame

    def _start_hackscript(
        self,
        track_path: Path,
        *,
        playback_pos_ms: int | None = None,
        playback_state: str = "playing",
    ) -> None:
        self._update_visualizer_viewport()
        resolved = track_path.expanduser()
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
        self._viz_request_id += 1
        request_id = self._viz_request_id
        logger.info(
            "Visualizer start name=%s size=%sx%s",
            self._viz_name,
            self._viewport_width,
            self._viewport_height,
        )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            frames = generate_hackscript(
                resolved,
                (self._viewport_width, self._viewport_height),
                prefs,
                viz_name=self._viz_name,
            )
            self._frame_player.start(frames)
            return

        async def prepare_frames() -> None:
            try:
                frames, first_frame = await asyncio.to_thread(
                    self._prepare_hackscript_frames,
                    resolved,
                    (self._viewport_width, self._viewport_height),
                    prefs,
                )
            except Exception as exc:
                logger.exception("Visualizer prep failed")
                if request_id == self._viz_request_id:
                    self._set_message(f"Visualizer error: {exc}", level="error")
                return
            if request_id != self._viz_request_id:
                return
            if frames is None or first_frame is None:
                return
            self._frame_player.start(frames, first_frame=first_frame)

        self.run_worker(prepare_frames(), exclusive=False)

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
        self._last_visualizer_key = None
        self._viz_prefs = {}
        self._viz_request_id += 1
        logger.info("Visualizer stop")
        if self._viz_restart_timer is not None:
            stopper = getattr(self._viz_restart_timer, "stop", None)
            if callable(stopper):
                stopper()
            self._viz_restart_timer = None
        self._refresh_visualizer(force=True)

    def _list_visualizations(self) -> list[str]:
        try:
            package = importlib.import_module("rhythm_slicer.visualizations")
        except Exception:
            return [self._viz_name or "hackscope"]
        names: list[str] = []
        for module_info in pkgutil.iter_modules(package.__path__):
            name = module_info.name
            try:
                module = importlib.import_module(f"rhythm_slicer.visualizations.{name}")
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


# UI components
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
            label_text = str(label)
            event.button.label = (
                "Save absolute paths: Off"
                if "On" in label_text
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
                    absolute = "On" in str(button.label)
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
                    absolute = "On" in str(button.label)
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


# Public entrypoints
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
