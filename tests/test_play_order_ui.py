from __future__ import annotations

import random

from rhythm_slicer.ui.play_order import build_play_order


def test_build_play_order_empty() -> None:
    order, pos = build_play_order(0, 0, False, random.Random(1))
    assert order == []
    assert pos == -1


def test_build_play_order_missing_current_index() -> None:
    order, pos = build_play_order(3, 99, False, random.Random(1))
    assert order == [0, 1, 2]
    assert pos == 0


def test_build_play_order_shuffle_keeps_current() -> None:
    rng = random.Random(2)
    order, pos = build_play_order(5, 3, True, rng)
    assert order[pos] == 3
