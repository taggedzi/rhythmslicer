"""UI tests for PlaylistBuilderScreen."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App
from textual import events
from textual.widget import Widget
from textual.widgets import Button

from rhythm_slicer.playlist import Playlist
from rhythm_slicer.ui import playlist_builder
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

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._start_path = start_path
        self.playlist = Playlist([])

    def on_mount(self) -> None:
        self.call_later(self.push_screen, PlaylistBuilderScreen(self._start_path))


async def _wait_for_builder(app: BuilderTestApp, pilot) -> None:
    for _ in range(50):
        if isinstance(app.screen, PlaylistBuilderScreen):
            return
        await pilot.pause(0.01)
    raise AssertionError("PlaylistBuilderScreen did not become active.")


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
