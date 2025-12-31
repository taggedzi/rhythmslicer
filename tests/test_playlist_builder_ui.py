"""UI tests for PlaylistBuilderScreen."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from textual.app import App
from textual import events
from textual.widget import Widget
from textual.widgets import Button, DataTable

from rhythm_slicer.playlist import Playlist, Track
from rhythm_slicer import playlist_builder as scan_builder
from rhythm_slicer.ui import playlist_builder
from rhythm_slicer.ui.marquee import Marquee
from rhythm_slicer.ui.playlist_builder import PlaylistBuilderScreen


class DummyBrowser(Widget):
    def __init__(self, start_path: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._selected_path: Path | None = None

    @property
    def selected_path(self) -> Path | None:
        return self._selected_path

    def set_selected_path(self, path: Path | None) -> None:
        self._selected_path = path


class BuilderTestApp(App):
    CSS = ""

    def __init__(self, start_path: Path, playlist: Playlist | None = None) -> None:
        super().__init__()
        self._start_path = start_path
        self.playlist = playlist or Playlist([])

    def on_mount(self) -> None:
        self.call_later(self.push_screen, PlaylistBuilderScreen(self._start_path))


class DummyPlayer:
    def __init__(self) -> None:
        self.stop_calls = 0

    def stop(self) -> None:
        self.stop_calls += 1


class BuilderPlaybackApp(BuilderTestApp):
    def __init__(self, start_path: Path, playlist: Playlist | None = None) -> None:
        super().__init__(start_path, playlist=playlist)
        self.player = DummyPlayer()
        self._playing_index: int | None = None

    def action_stop(self) -> None:
        self.player.stop()
        self._playing_index = None


@pytest.fixture(autouse=True)
def _disable_windows_hidden_attrs(monkeypatch) -> None:
    if scan_builder.sys.platform.startswith("win"):
        monkeypatch.setattr(scan_builder, "_windows_file_attributes", lambda _: 0)


async def _wait_for_builder(app: BuilderTestApp, pilot) -> None:
    for _ in range(50):
        if isinstance(app.screen, PlaylistBuilderScreen):
            return
        await pilot.pause(0.01)
    raise AssertionError("PlaylistBuilderScreen did not become active.")


async def _wait_for_selector(app: BuilderTestApp, pilot, selector: str) -> None:
    for _ in range(50):
        try:
            app.query_one(selector)
            return
        except Exception:
            await pilot.pause(0.01)
    raise AssertionError(f"Selector not found: {selector}")


def test_playlist_builder_add_directory_recursively(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "outer.mp3").write_text("x", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "inner.wav").write_text("x", encoding="utf-8")

    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)

    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            file_browser = app.screen.query_one("#builder_file_browser", DummyBrowser)
            file_browser.set_selected_path(tmp_path)
            add_button = app.screen.query_one("#builder_files_add", Button)
            app.screen.on_button_pressed(Button.Pressed(add_button))
            await pilot.pause()
            names = sorted(track.path.name for track in app.playlist.tracks)
            assert names == ["inner.wav", "outer.mp3"]

    asyncio.run(runner())


def test_playlist_builder_hidden_path_confirm_continue(
    tmp_path: Path, monkeypatch
) -> None:
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "secret.mp3").write_text("x", encoding="utf-8")

    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)

    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            captured: dict[str, object] = {}

            def fake_push_screen(screen, callback=None, wait_for_dismiss=False):
                captured["screen"] = screen
                if callback:
                    callback(True)
                return None

            app.push_screen = fake_push_screen  # type: ignore[assignment]
            file_browser = app.screen.query_one("#builder_file_browser", DummyBrowser)
            file_browser.set_selected_path(hidden)
            app.screen.query_one("#builder_files_add", Button).press()
            await pilot.pause()
            assert isinstance(
                captured.get("screen"), playlist_builder.HiddenPathConfirm
            )
            names = [track.path.name for track in app.playlist.tracks]
            assert names == ["secret.mp3"]

    asyncio.run(runner())


def test_playlist_builder_hidden_path_confirm_cancel(
    tmp_path: Path, monkeypatch
) -> None:
    hidden = tmp_path / ".hidden"
    hidden.mkdir()
    (hidden / "secret.mp3").write_text("x", encoding="utf-8")

    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)

    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            captured: dict[str, object] = {}

            def fake_push_screen(screen, callback=None, wait_for_dismiss=False):
                captured["screen"] = screen
                if callback:
                    callback(False)
                return None

            app.push_screen = fake_push_screen  # type: ignore[assignment]
            file_browser = app.screen.query_one("#builder_file_browser", DummyBrowser)
            file_browser.set_selected_path(hidden)
            app.screen.query_one("#builder_files_add", Button).press()
            await pilot.pause()
            assert isinstance(
                captured.get("screen"), playlist_builder.HiddenPathConfirm
            )
            assert app.playlist.tracks == []

    asyncio.run(runner())


def test_playlist_builder_escape_exits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)

    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            app.screen.on_key(events.Key("escape", None))
            await pilot.pause()
            assert not isinstance(app.screen, PlaylistBuilderScreen)

    asyncio.run(runner())


def test_playlist_builder_done_button_exits(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)

    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            done_button = app.screen.query_one("#builder_done", Button)
            app.screen.on_button_pressed(Button.Pressed(done_button))
            await pilot.pause()
            assert not isinstance(app.screen, PlaylistBuilderScreen)

    asyncio.run(runner())


def _build_track(path: Path) -> Track:
    return Track(path=path, title=path.stem)


def test_playlist_builder_move_up_button_moves_selection(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / name for name in ("a.mp3", "b.mp3", "c.mp3")]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderTestApp(tmp_path, playlist=playlist)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            app.screen._playlist_selection = {1}
            app.screen._refresh_playlist_entries()
            move_up = app.screen.query_one("#builder_playlist_move_up", Button)
            app.screen.on_button_pressed(Button.Pressed(move_up))
            await pilot.pause()
            assert [track.path.name for track in app.playlist.tracks] == [
                "b.mp3",
                "a.mp3",
                "c.mp3",
            ]

    asyncio.run(runner())


def test_playlist_builder_move_down_button_moves_selection(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / name for name in ("a.mp3", "b.mp3", "c.mp3")]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderTestApp(tmp_path, playlist=playlist)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            app.screen._playlist_selection = {1}
            app.screen._refresh_playlist_entries()
            move_down = app.screen.query_one("#builder_playlist_move_down", Button)
            app.screen.on_button_pressed(Button.Pressed(move_down))
            await pilot.pause()
            assert [track.path.name for track in app.playlist.tracks] == [
                "a.mp3",
                "c.mp3",
                "b.mp3",
            ]

    asyncio.run(runner())


def test_playlist_builder_selection_toggle_preserves_scroll(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / f"track_{i}.mp3" for i in range(60)]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderTestApp(tmp_path, playlist=playlist)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            table = app.screen.query_one("#builder_playlist", DataTable)
            table.move_cursor(row=40, column=0, scroll=False)
            table.scroll_to(y=10, animate=False, immediate=True)
            await pilot.pause()
            before_cursor = table.cursor_row
            before_scroll = table.scroll_y
            app.screen._toggle_playlist_selection()
            await pilot.pause()
            assert table.cursor_row == before_cursor
            assert table.scroll_y == before_scroll

    asyncio.run(runner())


def test_playlist_builder_highlight_updates_details(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / name for name in ("one.mp3", "two.mp3")]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderTestApp(tmp_path, playlist=playlist)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            table = app.screen.query_one("#builder_playlist", DataTable)
            table.move_cursor(row=1, column=0, scroll=False)
            event = DataTable.RowHighlighted(table, 1, "1")
            app.screen.on_data_table_row_highlighted(event)
            await pilot.pause()
            details = app.screen.query_one("#builder_playlist_details", Marquee)
            assert paths[1].name in details.current_text
            assert str(paths[1]) in details.full_text

    asyncio.run(runner())


def test_playlist_builder_remove_highlighted_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / name for name in ("a.mp3", "b.mp3", "c.mp3")]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderTestApp(tmp_path, playlist=playlist)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            table = app.screen.query_one("#builder_playlist", DataTable)
            table.move_cursor(row=1, column=0, scroll=False)
            remove_button = app.screen.query_one("#builder_playlist_remove", Button)
            app.screen.on_button_pressed(Button.Pressed(remove_button))
            await pilot.pause()
            assert [track.path.name for track in app.playlist.tracks] == [
                "a.mp3",
                "c.mp3",
            ]
            assert table.cursor_row == 1

    asyncio.run(runner())


def test_playlist_builder_remove_selected_rows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / name for name in ("a.mp3", "b.mp3", "c.mp3")]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderTestApp(tmp_path, playlist=playlist)
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            app.screen._playlist_selection = {0, 2}
            app.screen._refresh_playlist_entries()
            remove_button = app.screen.query_one("#builder_playlist_remove", Button)
            app.screen.on_button_pressed(Button.Pressed(remove_button))
            await pilot.pause()
            assert [track.path.name for track in app.playlist.tracks] == ["b.mp3"]
            assert app.screen._playlist_selection == set()

    asyncio.run(runner())


def test_playlist_builder_remove_playing_advances_to_next(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / name for name in ("a.mp3", "b.mp3", "c.mp3")]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderPlaybackApp(tmp_path, playlist=playlist)
        app._playing_index = 1
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            app.screen._playlist_selection = {1}
            app.screen._refresh_playlist_entries()
            remove_button = app.screen.query_one("#builder_playlist_remove", Button)
            app.screen.on_button_pressed(Button.Pressed(remove_button))
            await pilot.pause()
            assert app._playing_index == 1
            assert app.playlist.tracks[1].path.name == "c.mp3"
            assert app.player.stop_calls == 0

    asyncio.run(runner())


def test_playlist_builder_remove_playing_last_moves_previous(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    paths = [tmp_path / name for name in ("a.mp3", "b.mp3", "c.mp3")]
    for path in paths:
        path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path) for path in paths])

    async def runner() -> None:
        app = BuilderPlaybackApp(tmp_path, playlist=playlist)
        app._playing_index = 2
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            app.screen._playlist_selection = {2}
            app.screen._refresh_playlist_entries()
            remove_button = app.screen.query_one("#builder_playlist_remove", Button)
            app.screen.on_button_pressed(Button.Pressed(remove_button))
            await pilot.pause()
            assert app._playing_index == 1
            assert app.playlist.tracks[1].path.name == "b.mp3"
            assert app.player.stop_calls == 0

    asyncio.run(runner())


def test_playlist_builder_remove_last_track_stops(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(playlist_builder, "FileBrowserWidget", DummyBrowser)
    path = tmp_path / "a.mp3"
    path.write_text("x", encoding="utf-8")
    playlist = Playlist([_build_track(path)])

    async def runner() -> None:
        app = BuilderPlaybackApp(tmp_path, playlist=playlist)
        app._playing_index = 0
        async with app.run_test() as pilot:
            await _wait_for_builder(app, pilot)
            remove_button = app.screen.query_one("#builder_playlist_remove", Button)
            app.screen.on_button_pressed(Button.Pressed(remove_button))
            await pilot.pause()
            assert app.playlist.is_empty()
            assert app._playing_index is None
            assert app.player.stop_calls == 1

    asyncio.run(runner())
