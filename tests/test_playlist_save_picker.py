"""Tests for the playlist save picker helpers."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.playlist import M3U_EXTENSIONS
from rhythm_slicer.ui.playlist_save_picker import (
    build_save_result,
    compute_destination_path,
    save_mode_from_flag,
)


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
