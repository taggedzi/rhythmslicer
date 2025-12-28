"""Play order helpers for the TUI."""

from __future__ import annotations

import random


def build_play_order(
    count: int,
    current_index: int,
    shuffle: bool,
    rng: random.Random,
) -> tuple[list[int], int]:
    """Build a play order and return the order plus the current position."""
    if count <= 0:
        return [], -1
    order = list(range(count))
    if shuffle and count > 1:
        rng.shuffle(order)
    try:
        position = order.index(current_index)
    except ValueError:
        position = 0
    return order, position
