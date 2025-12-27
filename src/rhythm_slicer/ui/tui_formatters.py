from __future__ import annotations

import math


def visualizer_bars(seed_ms: int, width: int, height: int) -> list[int]:
    """Return deterministic bar heights for the visualizer."""
    if width <= 0 or height <= 0:
        return []
    t = seed_ms / 1000.0
    bars: list[int] = []
    for col in range(width):
        base = math.sin(t * 2.0 + col * 0.7)
        mod = math.sin(t * 0.7 + col * 1.3 + (col % 3) * 0.5)
        value = (base + mod) / 2.0
        normalized = (value + 1.0) / 2.0
        level = int(normalized * height)
        bars.append(min(height, max(0, level)))
    return bars
