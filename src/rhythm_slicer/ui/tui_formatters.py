from __future__ import annotations

import math
from typing import Callable, Optional


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


def render_visualizer(bars: list[int], height: int) -> str:
    """Render bar heights into a multi-line ASCII visualizer."""
    if height <= 0 or not bars:
        return ""
    width = len(bars)
    lines: list[str] = []
    for row in range(height):
        threshold = height - row
        line = "".join("#" if bars[col] >= threshold else " " for col in range(width))
        lines.append(line)
    return "\n".join(lines)


def _format_time_ms(value: Optional[int]) -> Optional[str]:
    if value is None:
        return None
    total_seconds = max(0, value // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _display_state(state: str) -> str:
    return state.capitalize() if state else "Unknown"


def status_state_label(
    *,
    playback_state_label: Callable[[], str],
    shuffle: bool,
    repeat_mode: str,
) -> str:
    label = playback_state_label()
    return f"[ {label.ljust(7)} ]"


def playback_state_label(*, playback_state: str, loading: bool) -> str:
    if loading:
        return "LOADING"
    state = (playback_state or "").lower()
    if "playing" in state:
        return "PLAYING"
    if "paused" in state:
        return "PAUSED"
    if "stop" in state:
        return "STOPPED"
    return "STOPPED"


def ellipsize(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ""
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return "." * max_len
    return text[: max_len - 3] + "..."


def format_status_time(
    *,
    loading: bool,
    get_position_ms: Callable[[], Optional[int]],
    get_length_ms: Callable[[], Optional[int]],
) -> tuple[str, int]:
    if loading:
        return "--:-- / --:--", 0
    position_ms = get_position_ms()
    length_ms = get_length_ms()
    if not length_ms or length_ms <= 0 or position_ms is None:
        return "--:-- / --:--", 0
    position_ms = max(0, position_ms)
    length_ms = max(0, length_ms)
    ratio = min(1.0, position_ms / float(length_ms)) if length_ms else 0.0
    progress = int(ratio * 100)
    position_text = _format_time_ms(position_ms) or "--:--"
    length_text = _format_time_ms(length_ms) or "--:--"
    return f"{position_text} / {length_text}", progress


def ratio_from_click(x: int, width: int) -> float:
    """Map a click x position to a 0..1 ratio."""
    if width <= 1:
        return 0.0
    clamped = max(0, min(x, width - 1))
    return clamped / float(width - 1)


def render_status_bar(width: int, ratio: float) -> str:
    if width <= 1:
        return "█"[:width]
    width = max(1, width)
    inner = max(1, width - 2)
    filled = int(max(0.0, min(1.0, ratio)) * inner)
    bar = "=" * filled + "-" * max(0, inner - filled)
    return f"[{bar}]" if width >= 2 else bar


def target_ms_from_ratio(length_ms: int, ratio: float) -> int:
    """Return a target time in ms for a ratio of track length."""
    return int(max(0.0, min(1.0, ratio)) * max(0, length_ms))
