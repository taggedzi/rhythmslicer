"""Tests for tui_widgets helpers."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from textual.app import App
from textual.widgets import Button

from rhythm_slicer.playlist_store_sqlite import TrackRow
from rhythm_slicer.ui.tui_widgets import PlaylistTable, TransportControls


class DummyPlayer:
    def __init__(self, state: str) -> None:
        self.state = state

    def get_state(self) -> str:
        return self.state


class TransportApp(App):
    CSS = ""

    def __init__(
        self, state: str, playlist_count: int, *, loading: bool = False
    ) -> None:
        super().__init__()
        self.player = DummyPlayer(state)
        self._playlist_count = playlist_count
        self._loading = loading
        self.calls = {"prev": 0, "playpause": 0, "stop": 0, "next": 0}

    def compose(self):
        yield TransportControls(id="transport_controls_widget")

    def action_previous_track(self) -> None:
        self.calls["prev"] += 1

    def action_toggle_playback(self) -> None:
        self.calls["playpause"] += 1

    def action_stop(self) -> None:
        self.calls["stop"] += 1

    def action_next_track(self) -> None:
        self.calls["next"] += 1


class PlaylistTableApp(App):
    CSS = ""

    def __init__(self, rows: list[TrackRow]) -> None:
        super().__init__()
        self._rows = rows
        self.lockout_calls = 0

    def compose(self):
        yield PlaylistTable(id="playlist_table")

    def on_mount(self) -> None:
        table = self.query_one("#playlist_table", PlaylistTable)
        table.set_tracks(self._rows)

    def _set_user_navigation_lockout(self) -> None:
        self.lockout_calls += 1


def _row(track_id: int, path: Path) -> TrackRow:
    return TrackRow(
        track_id=track_id,
        path=path,
        title=path.name,
        artist=None,
        album=None,
        duration_seconds=None,
        has_metadata=False,
    )


def test_transport_controls_actions_and_state(tmp_path: Path) -> None:
    result: dict[str, TransportApp] = {}

    async def runner() -> None:
        app = TransportApp("playing", playlist_count=2)
        async with app.run_test() as pilot:
            await pilot.pause()
            controls = app.query_one(TransportControls)
            controls.refresh_state()
            play_button = app.query_one("#transport_playpause", Button)
            assert str(play_button.label).strip() == "Pause"
            await pilot.click("#transport_prev")
            await pilot.click("#transport_playpause")
            await pilot.click("#transport_stop")
            await pilot.click("#transport_next")
            assert app.calls == {"prev": 1, "playpause": 1, "stop": 1, "next": 1}
            app._loading = True
            controls.refresh_state()
            assert play_button.disabled
            app._loading = False
            app._playlist_count = 0
            controls.refresh_state()
            assert play_button.disabled
            result["app"] = app

    asyncio.run(runner())
    assert result["app"].calls["prev"] == 1


def test_playlist_table_lockout_on_mouse_activity(tmp_path: Path) -> None:
    rows = [_row(1, tmp_path / "a.mp3"), _row(2, tmp_path / "b.mp3")]

    async def runner() -> None:
        app = PlaylistTableApp(rows)
        async with app.run_test() as pilot:
            await pilot.pause()
            table = app.query_one("#playlist_table", PlaylistTable)
            table.on_mouse_down(SimpleNamespace(y=0, stop=lambda: None))
            table.on_mouse_scroll_down(SimpleNamespace(stop=lambda: None))
            table.on_mouse_scroll_up(SimpleNamespace(stop=lambda: None))
            assert app.lockout_calls == 3
            assert table.cursor_index == 0

    asyncio.run(runner())
