"""Tests for the hackscope visualization plugin."""

from __future__ import annotations

import itertools
import re

from rhythm_slicer.visualizations import hackscope
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


def test_hackscope_resume_changes_first_frame() -> None:
    ctx_zero = VizContext(
        track_path="song.mp3",
        viewport_w=36,
        viewport_h=10,
        prefs={"fps": 20.0, "playback_pos_ms": 0},
        meta={"title": "Song", "artist": "Artist", "duration_sec": 120},
        seed=123,
    )
    ctx_resume = VizContext(
        track_path="song.mp3",
        viewport_w=36,
        viewport_h=10,
        prefs={"fps": 20.0, "playback_pos_ms": 60000},
        meta={"title": "Song", "artist": "Artist", "duration_sec": 120},
        seed=123,
    )
    frame_start = next(generate_frames(ctx_zero))
    frame_resume = next(generate_frames(ctx_resume))
    assert frame_start != frame_resume
    for frame in (frame_start, frame_resume):
        lines = _strip_sgr(frame).splitlines()
        assert len(lines) == ctx_zero.viewport_h
        assert all(len(line) == ctx_zero.viewport_w for line in lines)


def test_hackscope_resume_deterministic() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=34,
        viewport_h=8,
        prefs={"fps": 20.0, "playback_pos_ms": 45000},
        meta={"title": "Song", "artist": "Artist", "duration_sec": 180},
        seed=456,
    )
    frame_a = next(generate_frames(ctx))
    frame_b = next(generate_frames(ctx))
    assert frame_a == frame_b


def test_hackscope_resume_uses_locate_phase(monkeypatch) -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=40,
        viewport_h=10,
        prefs={
            "fps": 20.0,
            "playback_pos_ms": 600000,
            "hackscope_min_show_sec": 2000,
            "hackscope_max_show_sec": 2000,
            "hackscope_coverage": 1.0,
        },
        meta={"title": "Song", "artist": "Artist", "duration_sec": 2000},
        seed=789,
    )
    called = {"value": False}
    original = hackscope.locate_phase

    def wrapped(global_frame: int, phases: list[tuple[str, int]]) -> tuple[str, int]:
        called["value"] = True
        return original(global_frame, phases)

    monkeypatch.setattr(hackscope, "locate_phase", wrapped)
    frame = next(hackscope.generate_frames(ctx))
    assert frame
    assert called["value"]
