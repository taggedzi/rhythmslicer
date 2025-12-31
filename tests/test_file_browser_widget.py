"""Tests for FileBrowserWidget navigation."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys

from textual.app import App
from textual.widgets import DirectoryTree

from rhythm_slicer.ui.file_browser import FileBrowserWidget


class FileBrowserApp(App):
    CSS = ""

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._start_path = start_path

    def compose(self):
        yield FileBrowserWidget(self._start_path, id="file_browser")


def test_file_browser_up_from_root_switches_drive(tmp_path: Path, monkeypatch) -> None:
    other_root = tmp_path / "other_root"
    other_root.mkdir()
    root = Path(tmp_path.anchor)

    async def fake_prompt(self: FileBrowserWidget) -> Path | None:
        return other_root

    monkeypatch.setattr(FileBrowserWidget, "_prompt_for_drive", fake_prompt)

    async def runner() -> None:
        app = FileBrowserApp(root)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#file_browser_up")
            await pilot.pause()
            browser = app.query_one("#file_browser", FileBrowserWidget)
            tree = app.query_one("#file_browser_tree", DirectoryTree)
            expected_root = (
                Path(other_root.anchor)
                if sys.platform.startswith("win")
                else other_root
            )
            assert browser.current_directory == expected_root
            assert browser.selected_path == expected_root
            assert tree.path == expected_root

    asyncio.run(runner())


def test_file_browser_up_moves_to_parent(tmp_path: Path, monkeypatch) -> None:
    base = tmp_path / "base"
    child = base / "child"
    child.mkdir(parents=True)
    called = {"value": False}

    async def fake_prompt(self: FileBrowserWidget) -> Path | None:
        called["value"] = True
        return None

    monkeypatch.setattr(FileBrowserWidget, "_prompt_for_drive", fake_prompt)

    async def runner() -> None:
        app = FileBrowserApp(child)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#file_browser_up")
            await pilot.pause()
            browser = app.query_one("#file_browser", FileBrowserWidget)
            assert browser.current_directory == base
            assert browser.selected_path == base
            assert not called["value"]

    asyncio.run(runner())


def test_file_browser_drives_button_switches_root(tmp_path: Path, monkeypatch) -> None:
    start_path = tmp_path / "start"
    start_path.mkdir()
    other_root = tmp_path / "alt_root"
    other_root.mkdir()

    async def fake_prompt(self: FileBrowserWidget) -> Path | None:
        return other_root

    monkeypatch.setattr(FileBrowserWidget, "_prompt_for_drive", fake_prompt)

    async def runner() -> None:
        app = FileBrowserApp(start_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.click("#file_browser_drives")
            await pilot.pause()
            browser = app.query_one("#file_browser", FileBrowserWidget)
            tree = app.query_one("#file_browser_tree", DirectoryTree)
            expected_root = (
                Path(other_root.anchor)
                if sys.platform.startswith("win")
                else other_root
            )
            assert browser.current_directory == expected_root
            assert browser.selected_path == expected_root
            assert tree.path == expected_root

    asyncio.run(runner())
