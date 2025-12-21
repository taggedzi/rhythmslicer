"""Pytest configuration for RhythmSlicer."""

from __future__ import annotations

import os

import pytest


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    del config
    if os.environ.get("RHYTHM_SLICER_CI") != "1":
        return
    skip_vlc = pytest.mark.skip(reason="Skipping VLC-dependent tests in CI.")
    for item in items:
        if "vlc" in item.keywords:
            item.add_marker(skip_vlc)
