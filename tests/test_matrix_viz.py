"""Tests for the matrix visualization plugin."""

from __future__ import annotations

from rhythm_slicer.visualizations.host import VizContext
from rhythm_slicer.visualizations.matrix import generate_frames


def test_matrix_frame_dimensions() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=40,
        viewport_h=10,
        prefs={},
        meta={"title": "Song", "artist": "Artist"},
        seed=123,
    )
    frame = next(generate_frames(ctx))
    assert frame.count("\n") == ctx.viewport_h - 1
    lines = frame.splitlines()
    assert len(lines) == ctx.viewport_h
    assert all(len(line) == ctx.viewport_w for line in lines)
    assert "[Matrix]" in frame


def test_matrix_tiny_viewport() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=1,
        viewport_h=1,
        prefs={},
        meta={},
        seed=123,
    )
    frame = next(generate_frames(ctx))
    assert frame.count("\n") == 0
    lines = frame.splitlines()
    assert len(lines) == 1
    assert len(lines[0]) == 1
