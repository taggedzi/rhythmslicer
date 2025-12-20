"""Tests for visualization loading and minimal plugin."""

from __future__ import annotations

from rhythm_slicer.visualizations.host import VizContext
from rhythm_slicer.visualizations.loader import load_viz
from rhythm_slicer.visualizations import minimal


def test_loader_returns_minimal_when_builtin_missing() -> None:
    plugin = load_viz("missing")
    assert plugin.VIZ_NAME == minimal.VIZ_NAME


def test_loader_invalid_name_falls_back() -> None:
    for name in ("../x", "X", "", "a-b"):
        plugin = load_viz(name)
        assert plugin.VIZ_NAME == minimal.VIZ_NAME


def test_minimal_frames_match_dimensions() -> None:
    ctx = VizContext(
        track_path="song.mp3",
        viewport_w=12,
        viewport_h=4,
        prefs={},
        meta={"title": "Song", "artist": "Artist"},
        seed=123,
    )
    frame = next(minimal.generate_frames(ctx))
    lines = frame.splitlines()
    assert len(lines) == ctx.viewport_h
    assert all(len(line) == ctx.viewport_w for line in lines)
