"""Tests for ANSI sanitizer."""

from __future__ import annotations

from rhythm_slicer.visualizations.ansi import sanitize_ansi_sgr


def test_sanitize_ansi_sgr_keeps_only_sgr() -> None:
    text = "start\x1b[31mred\x1b[0m\x1b[2J\x1b]0;title\x07\x1b[Hend"
    sanitized = sanitize_ansi_sgr(text)
    assert "\x1b[31m" in sanitized
    assert "\x1b[0m" in sanitized
    assert "\x1b[2J" not in sanitized
    assert "\x1b]0;title\x07" not in sanitized
    assert "\x1b[H" not in sanitized
