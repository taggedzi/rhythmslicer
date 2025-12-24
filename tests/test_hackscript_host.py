"""Tests for HackScript visualization host."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer import hackscript


def test_hackscript_uses_minimal_viz(monkeypatch) -> None:
    monkeypatch.setattr(hackscript, "_extract_metadata", lambda _: {})
    frames = hackscript.run_generator(
        viz_name="minimal",
        track_path=Path("song.mp3"),
        viewport=(20, 4),
        prefs={},
        seed=123,
    )
    frame = next(frames)
    assert "RhythmSlicer" in frame
