"""UI tests for PlaylistBuilderScreen."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App

from rhythm_slicer.playlist import Playlist
from rhythm_slicer.ui.file_browser import FileBrowserWidget
from rhythm_slicer.ui.playlist_builder import PlaylistBuilderScreen


class BuilderTestApp(App):
    CSS = ""

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._start_path = start_path
        self.playlist = Playlist([])

    def on_mount(self) -> None:
        self.push_screen(PlaylistBuilderScreen(self._start_path))


def test_playlist_builder_add_directory_recursively(tmp_path: Path) -> None:
    (tmp_path / "outer.mp3").write_text("x", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    subdir = tmp_path / "sub"
    subdir.mkdir()
    (subdir / "inner.wav").write_text("x", encoding="utf-8")

    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            file_browser = app.query_one(FileBrowserWidget)
            file_browser.set_selected_path(tmp_path)
            await pilot.click("#builder_files_add")
            await pilot.pause()
            names = sorted(track.path.name for track in app.playlist.tracks)
            assert names == ["inner.wav", "outer.mp3"]

    asyncio.run(runner())


def test_playlist_builder_escape_exits(tmp_path: Path) -> None:
    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, PlaylistBuilderScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, PlaylistBuilderScreen)

    asyncio.run(runner())


def test_playlist_builder_done_button_exits(tmp_path: Path) -> None:
    async def runner() -> None:
        app = BuilderTestApp(tmp_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, PlaylistBuilderScreen)
            await pilot.click("#builder_done")
            await pilot.pause()
            assert not isinstance(app.screen, PlaylistBuilderScreen)

    asyncio.run(runner())
