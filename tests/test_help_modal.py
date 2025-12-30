"""Tests for help modal content."""

from __future__ import annotations

from rhythm_slicer.tui import RhythmSlicerApp
from rhythm_slicer.ui.help_modal import build_help_text


def test_help_text_includes_keybinds() -> None:
    text = build_help_text(RhythmSlicerApp.BINDINGS)
    plain = text.plain
    assert "Space — Play/Pause" in plain
    assert "Enter — Play Selected" in plain
    assert "V — Change visualization" in plain
    assert "Ctrl+O — Playlist Builder" in plain
    assert "Q — Quit" in plain
    assert "Open help" in plain
    assert "Logs — %LOCALAPPDATA%/RhythmSlicer/logs" in plain
