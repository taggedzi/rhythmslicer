from __future__ import annotations

from typing import TYPE_CHECKING, cast

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

if TYPE_CHECKING:
    from rhythm_slicer.tui import RhythmSlicerApp


class VisualizerHud(Static):
    """Compact HUD for the visualizer pane."""


class PlaylistTable(DataTable):
    """Playlist table with double-click play behavior."""

    async def _on_click(self, event: events.Click) -> None:
        if hasattr(self.app, "_set_user_navigation_lockout"):
            self.app._set_user_navigation_lockout()
        await super()._on_click(event)

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if hasattr(self.app, "_set_user_navigation_lockout"):
            self.app._set_user_navigation_lockout()
        super()._on_mouse_scroll_down(event)

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if hasattr(self.app, "_set_user_navigation_lockout"):
            self.app._set_user_navigation_lockout()
        super()._on_mouse_scroll_up(event)


class TransportControls(Static):
    """Transport controls for the playlist pane."""

    def _app(self) -> "RhythmSlicerApp":
        return cast(RhythmSlicerApp, self.app)

    def compose(self) -> ComposeResult:
        with Horizontal(id="transport_controls"):
            yield Button("Prev", id="transport_prev", classes="transport_button")
            yield Button("Play", id="transport_playpause", classes="transport_button")
            yield Button("Stop", id="transport_stop", classes="transport_button")
            yield Button("Next", id="transport_next", classes="transport_button")

    def on_mount(self) -> None:
        self.set_interval(0.25, self._refresh_label)
        self.refresh_state()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        control_id = event.button.id
        app = self._app()
        if control_id == "transport_prev":
            app.action_previous_track()
        elif control_id == "transport_playpause":
            app.action_toggle_playback()
        elif control_id == "transport_stop":
            app.action_stop()
        elif control_id == "transport_next":
            app.action_next_track()
        self.refresh_state()

    def _refresh_label(self) -> None:
        self.refresh_state()

    def refresh_state(self) -> None:
        try:
            label = self.query_one("#transport_playpause", Button)
            prev_button = self.query_one("#transport_prev", Button)
            stop_button = self.query_one("#transport_stop", Button)
            next_button = self.query_one("#transport_next", Button)
        except Exception:
            return
        app = self._app()
        state = (app.player.get_state() or "").lower()
        label.label = "Pause " if "playing" in state else "Play  "
        playlist = getattr(app, "playlist", None)
        is_loading = bool(getattr(app, "_loading", False))
        has_tracks = bool(playlist and not playlist.is_empty())
        is_playing = "playing" in state
        is_paused = "paused" in state
        prev_button.disabled = is_loading or not has_tracks
        next_button.disabled = is_loading or not has_tracks
        label.disabled = is_loading or not has_tracks
        stop_button.disabled = is_loading or not (
            has_tracks and (is_playing or is_paused)
        )
