"""Tests for visualization loading and minimal plugin."""

from __future__ import annotations

import importlib.metadata
from types import SimpleNamespace

from rhythm_slicer.visualizations.host import VizContext
from rhythm_slicer.visualizations import loader
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


def test_loader_uses_entry_point_select(monkeypatch) -> None:
    plugin = SimpleNamespace(
        VIZ_NAME="custom", generate_frames=lambda ctx: iter(["ok"])
    )

    class _EntryPoint:
        name = "custom"

        def load(self):
            return plugin

    class _EntryPoints:
        def select(self, group: str):
            assert group == "rhythmslicer.visualizations"
            return [_EntryPoint()]

    monkeypatch.setattr(loader, "_load_builtin", lambda _: None)
    monkeypatch.setattr(importlib.metadata, "entry_points", lambda: _EntryPoints())
    result = load_viz("custom")
    assert result is plugin


def test_loader_entry_point_errors_fall_back(monkeypatch) -> None:
    class _EntryPoint:
        name = "custom"

        def load(self):
            raise RuntimeError("bad")

    monkeypatch.setattr(loader, "_load_builtin", lambda _: None)
    monkeypatch.setattr(
        importlib.metadata,
        "entry_points",
        lambda: {"rhythmslicer.visualizations": [_EntryPoint()]},
    )
    result = load_viz("custom")
    assert result.VIZ_NAME == minimal.VIZ_NAME
