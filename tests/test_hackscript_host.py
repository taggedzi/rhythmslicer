"""Tests for HackScript visualization host."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.hackscript import run_generator


def test_hackscript_uses_minimal_viz() -> None:
    frames = run_generator(
        viz_name="minimal",
        track_path=Path("song.mp3"),
        viewport=(20, 4),
        prefs={},
        seed=123,
    )
    frame = next(frames)
    assert "RhythmSlicer" in frame
