"""Tests for the hackscope visualization plugin."""

from __future__ import annotations

import itertools
import re

from rhythm_slicer.visualizations.hackscope import generate_frames
from rhythm_slicer.visualizations.host import VizContext

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")


def _strip_sgr(text: str) -> str:
    return _SGR_PATTERN.sub("", text)


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
    lines = _strip_sgr(frame).splitlines()
    assert len(lines) == ctx.viewport_h
    assert all(len(line) == ctx.viewport_w for line in lines)
    assert ("HackScope" in _strip_sgr(frame)) or ("hackscript" in frame)


def test_hackscope_mid_show_frame() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=40,
        viewport_h=10,
        prefs={"fps": 20.0},
        meta={"title": "Song", "artist": "Artist", "duration_sec": 120},
        seed=123,
    )
    gen = generate_frames(ctx)
    frame = None
    for frame in itertools.islice(gen, 50):
        pass
    assert frame is not None
    stripped = _strip_sgr(frame)
    lines = stripped.splitlines()
    assert len(lines) == ctx.viewport_h
    assert all(len(line) == ctx.viewport_w for line in lines)
    assert "[HackScope]" in stripped


def test_hackscope_long_show_yields_many_frames() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=40,
        viewport_h=10,
        prefs={"fps": 20.0},
        meta={"duration_sec": 300},
        seed=123,
    )
    gen = generate_frames(ctx)
    frames = list(itertools.islice(gen, 201))
    assert len(frames) == 201


def test_hackscope_ansi_visible_width() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=32,
        viewport_h=8,
        prefs={"ansi_colors": True, "fps": 20.0},
        meta={"title": "Song", "artist": "Artist", "duration_sec": 120},
        seed=123,
    )
    gen = generate_frames(ctx)
    found = False
    for frame in itertools.islice(gen, 200):
        if "\x1b[" in frame:
            found = True
            stripped = _strip_sgr(frame)
            lines = stripped.splitlines()
            assert len(lines) == ctx.viewport_h
            assert all(len(line) == ctx.viewport_w for line in lines)
            break
    assert found
