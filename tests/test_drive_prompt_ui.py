"""UI tests for DrivePrompt."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from textual.app import App
from textual.widgets import Select

from rhythm_slicer.ui.drive_prompt import DrivePrompt


class DrivePromptApp(App):
    CSS = ""

    def __init__(self, drives: list[Path]) -> None:
        super().__init__()
        self._drives = drives

    def on_mount(self) -> None:
        self.push_screen(DrivePrompt(self._drives))


def test_drive_prompt_ok_returns_selected(tmp_path: Path) -> None:
    drive = tmp_path / "drive"
    drive.mkdir()
    result: dict[str, Path | None] = {}

    async def runner() -> None:
        app = DrivePromptApp([drive])
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DrivePrompt)
            screen.dismiss = lambda value: result.setdefault("value", value)
            await pilot.click("#drive_prompt_ok")
            await pilot.pause()

    asyncio.run(runner())
    assert result["value"] == drive


def test_drive_prompt_select_and_escape(tmp_path: Path) -> None:
    drive_a = tmp_path / "a"
    drive_b = tmp_path / "b"
    drive_a.mkdir()
    drive_b.mkdir()
    result: dict[str, Path | None] = {}

    async def runner() -> None:
        app = DrivePromptApp([drive_a, drive_b])
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, DrivePrompt)
            screen.dismiss = lambda value: result.setdefault("value", value)
            screen.on_select_changed(SimpleNamespace(value=Select.BLANK))
            assert screen._selected is None
            screen.on_select_changed(SimpleNamespace(value=str(drive_b)))
            assert screen._selected == drive_b
            screen.on_key(SimpleNamespace(key="escape", stop=lambda: None))
            await pilot.pause()

    asyncio.run(runner())
    assert result["value"] is None
