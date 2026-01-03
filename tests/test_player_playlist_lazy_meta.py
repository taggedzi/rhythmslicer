"""Tests for lazy metadata loading in the player playlist view."""

from __future__ import annotations

from pathlib import Path
import time
import threading

from rhythm_slicer.metadata import TrackMeta
from rhythm_slicer.ui.metadata_loader import MetadataLoader


def _wait_for(predicate, *, timeout: float = 1.0) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if predicate():
            return
        time.sleep(0.01)


def test_metadata_loader_limits_initial_requests() -> None:
    calls: list[Path] = []
    loader = MetadataLoader(
        load_meta=lambda path: calls.append(path) or TrackMeta("a", "t"),
        get_cached=lambda _: None,
        max_workers=1,
        queue_limit=50,
    )
    loader.start(lambda *_: None)
    loader.set_generation(1)

    paths = [Path(f"track_{idx}.mp3") for idx in range(10_000)]
    visible = paths[:8]
    loader.update_visible(visible)

    _wait_for(lambda: len(calls) >= len(visible))
    loader.stop()

    assert set(calls) == set(visible)


def test_metadata_loader_requests_visible_then_scrolled() -> None:
    calls: list[Path] = []
    loader = MetadataLoader(
        load_meta=lambda path: calls.append(path) or TrackMeta("a", "t"),
        get_cached=lambda _: None,
        max_workers=1,
        queue_limit=50,
    )
    loader.start(lambda *_: None)
    loader.set_generation(1)

    paths = [Path(f"track_{idx}.mp3") for idx in range(20)]
    first = paths[:4]
    loader.update_visible(first)
    _wait_for(lambda: len(calls) >= len(first))

    second = paths[10:14]
    loader.update_visible(second)
    _wait_for(lambda: len(calls) >= len(first) + len(second))
    loader.stop()

    assert set(calls) == set(first + second)


def test_metadata_loader_ignores_stale_generation_updates() -> None:
    calls: list[tuple[Path, int]] = []
    block = threading.Event()

    def fake_load(path: Path) -> TrackMeta:
        block.wait(timeout=1.0)
        return TrackMeta("a", "t")

    def notify(path: Path, _meta: TrackMeta | None, generation: int) -> None:
        calls.append((path, generation))

    loader = MetadataLoader(
        load_meta=fake_load,
        get_cached=lambda _: None,
        max_workers=1,
        queue_limit=10,
    )
    loader.start(notify)
    loader.set_generation(1)
    old_path = Path("old.mp3")
    loader.update_visible([old_path])
    time.sleep(0.05)
    loader.set_generation(2)
    new_path = Path("new.mp3")
    loader.update_visible([new_path])
    block.set()

    _wait_for(lambda: any(path == new_path for path, _ in calls))
    loader.stop()

    assert all(path != old_path for path, _ in calls)
