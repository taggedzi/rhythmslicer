"""Tests for the hackscope visualization plugin."""

from __future__ import annotations

from rhythm_slicer.visualizations.hackscope import generate_frames
from rhythm_slicer.visualizations.host import VizContext


def test_hackscope_first_frame_dimensions() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=40,
        viewport_h=10,
        prefs={},
        meta={"title": "Song", "artist": "Artist"},
        seed=123,
    )
    frame = next(generate_frames(ctx))
    lines = frame.splitlines()
    assert len(lines) == ctx.viewport_h
    assert all(len(line) == ctx.viewport_w for line in lines)
    assert ("HackScope" in frame) or ("hackscript" in frame)
