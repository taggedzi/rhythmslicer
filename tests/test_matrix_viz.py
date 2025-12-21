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


def test_matrix_paused_freezes_frames() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=20,
        viewport_h=6,
        prefs={
            "fps": 20.0,
            "playback_pos_ms": 15000,
            "playback_state": "paused",
        },
        meta={},
        seed=123,
    )
    gen = generate_frames(ctx)
    frames = [next(gen) for _ in range(3)]
    assert frames[0] == frames[1] == frames[2]
    lines = frames[0].splitlines()
    assert len(lines) == ctx.viewport_h
    assert all(len(line) == ctx.viewport_w for line in lines)


def test_matrix_playing_advances_frames() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=20,
        viewport_h=6,
        prefs={
            "fps": 20.0,
            "playback_pos_ms": 0,
            "playback_state": "playing",
        },
        meta={},
        seed=123,
    )
    gen = generate_frames(ctx)
    first = next(gen)
    second = next(gen)
    assert first != second
