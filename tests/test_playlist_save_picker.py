"""Tests for the playlist save picker helpers and UI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from textual.app import App
from textual.widgets import Button, Input

from rhythm_slicer.playlist import M3U_EXTENSIONS
from rhythm_slicer.ui.playlist_save_picker import (
    PlaylistSavePicker,
    SaveResult,
    _append_default_extension,
    _normalize_extension,
    _normalize_filename,
    build_save_result,
    compute_destination_path,
    save_mode_from_flag,
)


class PlaylistSavePickerApp(App):
    CSS = ""

    def __init__(self, start_directory: Path, filename: str) -> None:
        super().__init__()
        self._start_directory = start_directory
        self._filename = filename

    def on_mount(self) -> None:
        self.push_screen(PlaylistSavePicker(self._start_directory, self._filename))


async def _wait_for_picker(app: PlaylistSavePickerApp, pilot) -> PlaylistSavePicker:
    for _ in range(50):
        screen = app.screen
        if isinstance(screen, PlaylistSavePicker):
            return screen
        await pilot.pause(0.01)
    raise AssertionError("PlaylistSavePicker did not become active.")


async def _wait_for_selector(screen: PlaylistSavePicker, pilot, selector: str) -> None:
    for _ in range(50):
        try:
            screen.query_one(selector)
            return
        except Exception:
            await pilot.pause(0.01)
    raise AssertionError(f"Selector not found: {selector}")


def test_normalize_helpers() -> None:
    assert _normalize_extension("m3u") == ".m3u"
    assert _normalize_extension(".m3u8") == ".m3u8"
    assert _normalize_extension("") == ""
    assert _normalize_filename("  ") == ""
    assert _normalize_filename(" ../mix.m3u8 ") == "mix.m3u8"


def test_append_default_extension_prefers_allowed() -> None:
    assert _append_default_extension("mix", ".pls", [".m3u8", ".m3u"]) == "mix.m3u8"
    assert _append_default_extension("mix.m3u", ".m3u8", [".m3u8"]) == "mix.m3u"
    assert _append_default_extension("", ".m3u8", [".m3u8"]) == ""


def test_compute_destination_appends_default_extension(tmp_path: Path) -> None:
    dest = compute_destination_path(
        tmp_path,
        "mix",
        default_extension=".m3u8",
        allowed_extensions=M3U_EXTENSIONS,
    )
    assert dest == tmp_path / "mix.m3u8"


def test_compute_destination_keeps_existing_extension(tmp_path: Path) -> None:
    dest = compute_destination_path(
        tmp_path,
        "mix.m3u",
        default_extension=".m3u8",
        allowed_extensions=M3U_EXTENSIONS,
    )
    assert dest == tmp_path / "mix.m3u"


def test_save_result_preserves_absolute_flag(tmp_path: Path) -> None:
    result = build_save_result(
        tmp_path,
        "mix",
        save_absolute=True,
        default_extension=".m3u8",
        allowed_extensions=M3U_EXTENSIONS,
    )
    assert result.save_absolute is True
    assert save_mode_from_flag(result.save_absolute) == "absolute"


def test_playlist_save_picker_save_flow(tmp_path: Path) -> None:
    start_dir = tmp_path / "start"
    other_dir = tmp_path / "other"
    start_dir.mkdir()
    other_dir.mkdir()
    file_path = other_dir / "mix.m3u8"
    file_path.write_text("x", encoding="utf-8")
    result: dict[str, SaveResult | None] = {}

    async def runner() -> None:
        app = PlaylistSavePickerApp(start_dir, "setlist")
        async with app.run_test() as pilot:
            screen = await _wait_for_picker(app, pilot)
            screen.dismiss = lambda value: result.setdefault("value", value)
            await _wait_for_selector(screen, pilot, "#save_picker_filename")
            input_widget = screen.query_one("#save_picker_filename", Input)
            input_widget.value = " "
            screen.on_input_changed(SimpleNamespace(input=input_widget))
            save_button = screen.query_one("#save_picker_save", Button)
            assert save_button.disabled
            input_widget.value = "setlist"
            screen.on_input_changed(SimpleNamespace(input=input_widget))
            screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="save_picker_absolute"))
            )
            absolute_button = screen.query_one("#save_picker_absolute", Button)
            assert "On" in str(absolute_button.label)
            screen.on_directory_tree_directory_selected(SimpleNamespace(path=other_dir))
            input_widget.value = ""
            screen.on_directory_tree_file_selected(SimpleNamespace(path=file_path))
            screen.on_button_pressed(
                SimpleNamespace(button=SimpleNamespace(id="save_picker_save"))
            )
            await pilot.pause()

    asyncio.run(runner())
    assert isinstance(result["value"], SaveResult)
    assert result["value"].target_path == file_path
    assert result["value"].save_absolute is True


def test_playlist_save_picker_escape_cancels(tmp_path: Path) -> None:
    start_dir = tmp_path / "start"
    start_dir.mkdir()
    result: dict[str, SaveResult | None] = {}

    async def runner() -> None:
        app = PlaylistSavePickerApp(start_dir, "mix")
        async with app.run_test() as pilot:
            screen = await _wait_for_picker(app, pilot)
            screen.dismiss = lambda value: result.setdefault("value", value)
            screen.on_key(SimpleNamespace(key="escape"))
            await pilot.pause()

    asyncio.run(runner())
    assert result["value"] is None
