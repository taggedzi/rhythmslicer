"""Tests for playlist file picker helpers and UI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from textual.app import App
from textual.widgets import Button, ListView

from rhythm_slicer.ui.playlist_file_picker import (
    PlaylistFileItem,
    PlaylistFilePicker,
    filter_playlist_filenames,
    pick_start_directory,
    playlist_files_in_directory,
)


class PlaylistFilePickerApp(App):
    CSS = ""

    def __init__(self, start_directory: Path) -> None:
        super().__init__()
        self._start_directory = start_directory

    def on_mount(self) -> None:
        self.push_screen(PlaylistFilePicker(self._start_directory))


async def _wait_for_picker(app: PlaylistFilePickerApp, pilot) -> PlaylistFilePicker:
    for _ in range(50):
        screen = app.screen
        if isinstance(screen, PlaylistFilePicker):
            return screen
        await pilot.pause(0.01)
    raise AssertionError("PlaylistFilePicker did not become active.")


async def _wait_for_selector(screen: PlaylistFilePicker, pilot, selector: str) -> None:
    for _ in range(50):
        try:
            screen.query_one(selector)
            return
        except Exception:
            await pilot.pause(0.01)
    raise AssertionError(f"Selector not found: {selector}")


async def _wait_for_no_items(
    list_view: ListView, pilot, *, timeout: float = 0.5
) -> None:
    for _ in range(int(timeout / 0.01)):
        if not any(isinstance(child, PlaylistFileItem) for child in list_view.children):
            return
        await pilot.pause(0.01)
    raise AssertionError("Playlist items were not cleared.")


def test_filter_playlist_filenames() -> None:
    names = ["mix.m3u", "mix.m3u8", "track.mp3", "README.M3U", "notes.txt"]
    assert filter_playlist_filenames(names) == ["mix.m3u", "mix.m3u8", "README.M3U"]


def test_pick_start_directory_uses_last_parent(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    playlist_dir.mkdir()
    last_path = playlist_dir / "set.m3u8"
    last_path.write_text("x", encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    assert pick_start_directory(last_path, cwd) == playlist_dir


def test_pick_start_directory_uses_last_dir(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    playlist_dir.mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    assert pick_start_directory(playlist_dir, cwd) == playlist_dir


def test_pick_start_directory_falls_back_to_cwd(tmp_path: Path) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    missing = tmp_path / "missing" / "list.m3u"
    assert pick_start_directory(missing, cwd) == cwd


def test_playlist_files_in_directory(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    playlist_dir.mkdir()
    (playlist_dir / "b.m3u").write_text("x", encoding="utf-8")
    (playlist_dir / "a.m3u8").write_text("x", encoding="utf-8")
    (playlist_dir / "ignore.txt").write_text("x", encoding="utf-8")
    results = playlist_files_in_directory(playlist_dir)
    assert [path.name for path in results] == ["a.m3u8", "b.m3u"]


def test_playlist_file_picker_selection_and_confirm(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    playlist_dir.mkdir()
    (playlist_dir / "b.m3u").write_text("x", encoding="utf-8")
    (playlist_dir / "a.m3u8").write_text("x", encoding="utf-8")
    result: dict[str, Path | None] = {}
    expected = playlist_dir / "a.m3u8"

    async def runner() -> None:
        app = PlaylistFilePickerApp(playlist_dir)
        async with app.run_test() as pilot:
            screen = await _wait_for_picker(app, pilot)
            screen.dismiss = lambda value: result.setdefault("value", value)
            await _wait_for_selector(screen, pilot, "#playlist_file_list")
            list_view = screen.query_one("#playlist_file_list", ListView)
            assert len(list_view.children) == 2
            first_item = list_view.children[0]
            screen.on_list_view_highlighted(SimpleNamespace(item=first_item))
            ok_button = screen.query_one("#playlist_file_ok", Button)
            assert not ok_button.disabled
            screen.on_key(SimpleNamespace(key="enter"))
            await pilot.pause()

    asyncio.run(runner())
    assert result["value"] == expected


def test_playlist_file_picker_directory_refresh_and_cancel(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    empty_dir = tmp_path / "empty"
    playlist_dir.mkdir()
    empty_dir.mkdir()
    (playlist_dir / "mix.m3u").write_text("x", encoding="utf-8")
    result: dict[str, Path | None] = {}

    async def runner() -> None:
        app = PlaylistFilePickerApp(playlist_dir)
        async with app.run_test() as pilot:
            screen = await _wait_for_picker(app, pilot)
            screen.dismiss = lambda value: result.setdefault("value", value)
            screen.on_directory_tree_directory_selected(SimpleNamespace(path=empty_dir))
            await _wait_for_selector(screen, pilot, "#playlist_file_list")
            list_view = screen.query_one("#playlist_file_list", ListView)
            await _wait_for_no_items(list_view, pilot)
            ok_button = screen.query_one("#playlist_file_ok", Button)
            assert ok_button.disabled
            screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="playlist_file_cancel"))
            )
            await pilot.pause()

    asyncio.run(runner())
    assert result["value"] is None


def test_playlist_file_picker_double_click_confirms(tmp_path: Path) -> None:
    playlist_dir = tmp_path / "lists"
    playlist_dir.mkdir()
    (playlist_dir / "mix.m3u8").write_text("x", encoding="utf-8")
    result: dict[str, Path | None] = {}
    expected = playlist_dir / "mix.m3u8"

    async def runner() -> None:
        app = PlaylistFilePickerApp(playlist_dir)
        async with app.run_test() as pilot:
            screen = await _wait_for_picker(app, pilot)
            screen.dismiss = lambda value: result.setdefault("value", value)
            await _wait_for_selector(screen, pilot, "#playlist_file_list")
            list_view = screen.query_one("#playlist_file_list", ListView)
            item = list_view.children[0]
            screen.on_click(SimpleNamespace(widget=item, clicks=2))
            await pilot.pause()

    asyncio.run(runner())
    assert result["value"] == expected
