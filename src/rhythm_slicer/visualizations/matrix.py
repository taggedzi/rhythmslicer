"""Deterministic Matrix-style ASCII visualization."""

from __future__ import annotations

from pathlib import Path
import random
from typing import Iterator

from rhythm_slicer.visualizations.host import VizContext

VIZ_NAME = "matrix"
VIZ_TITLE = "Matrix"
VIZ_DESCRIPTION = "Deterministic green-rain style ASCII columns"

_DEFAULT_CHARSET = (
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#$%&*+-/\\|"
)


def _clamp_float(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _header_line(ctx: VizContext, width: int) -> str:
    meta = ctx.meta if isinstance(ctx.meta, dict) else {}
    title = meta.get("title") or Path(ctx.track_path).name
    artist = meta.get("artist")
    if artist:
        text = f"[Matrix] {title}  {artist}"
    else:
        text = f"[Matrix] {title}"
    if len(text) > width:
        text = text[:width]
    return text.ljust(width)


def _new_drop(rng: random.Random, height: int) -> dict[str, float | int | bool]:
    if height <= 0:
        return {"active": False, "y": 0.0, "speed": 0.0, "trail": 0}
    y = rng.uniform(-height, 0.0)
    speed = rng.uniform(0.4, 1.2)
    trail = rng.randint(3, max(3, height // 2))
    return {"active": True, "y": y, "speed": speed, "trail": trail}


def generate_frames(ctx: VizContext) -> Iterator[str]:
    width = max(1, int(ctx.viewport_w))
    height = max(1, int(ctx.viewport_h))
    prefs = ctx.prefs if isinstance(ctx.prefs, dict) else {}
    state = str(prefs.get("playback_state", "playing")).lower()
    paused = state == "paused"
    header_enabled = bool(prefs.get("matrix_header", True))
    density = prefs.get("matrix_density", 0.55)
    try:
        density = float(density)
    except Exception:
        density = 0.55
    density = _clamp_float(density, 0.0, 1.0)
    fps = prefs.get("fps", 20.0)
    try:
        fps_value = float(fps)
    except Exception:
        fps_value = 20.0
    fps_value = max(1.0, fps_value)
    start_ms = int(prefs.get("playback_pos_ms", 0) or 0)
    start_frame = max(0, int((start_ms / 1000.0) * fps_value))
    speed_mult = prefs.get("matrix_speed", 1.0)
    try:
        speed_mult = float(speed_mult)
    except Exception:
        speed_mult = 1.0
    speed_mult = max(0.1, speed_mult)
    charset = prefs.get("matrix_charset")
    if not isinstance(charset, str) or not charset:
        charset = _DEFAULT_CHARSET

    rng = random.Random(ctx.seed if ctx.seed is not None else 0)
    rain_height = height - 1 if header_enabled and height > 1 else height

    drops: list[dict[str, float | int | bool]] = []
    for _ in range(width):
        if rng.random() < density:
            drops.append(_new_drop(rng, rain_height))
        else:
            drops.append({"active": False, "y": 0.0, "speed": 0.0, "trail": 0})

    spawn_rate = max(0.02, density * 0.08)

    def render_frame() -> str:
        if header_enabled:
            header = _header_line(ctx, width)
            if height == 1:
                return header
            lines = ["".join(row).ljust(width) for row in grid]
            while len(lines) < rain_height:
                lines.append(" " * width)
            return "\n".join([header] + lines[:rain_height])
        if height == 1:
            if rain_height == 0:
                return " " * width
            line = "".join(grid[0]) if grid else ""
            return line.ljust(width)[:width]
        lines = ["".join(row).ljust(width) for row in grid]
        while len(lines) < height:
            lines.append(" " * width)
        return "\n".join(lines[:height])

    def step_frame() -> str:
        nonlocal drops
        if rain_height > 0:
            new_grid = [[" " for _ in range(width)] for _ in range(rain_height)]
        else:
            new_grid = []
        for col in range(width):
            state = drops[col]
            active = bool(state.get("active"))
            if not active:
                if rng.random() < spawn_rate:
                    drops[col] = _new_drop(rng, rain_height)
                continue
            if rain_height <= 0:
                continue
            y = float(state.get("y", 0.0))
            speed = float(state.get("speed", 0.0))
            trail = int(state.get("trail", 0))
            y += speed * speed_mult
            state["y"] = y
            head = int(y)
            tail = head - trail
            if tail > rain_height:
                state["active"] = False
                continue
            if head < 0:
                continue
            start = max(0, tail)
            end = min(rain_height - 1, head)
            for row in range(start, end + 1):
                ch = charset[rng.randrange(len(charset))]
                new_grid[row][col] = ch
        if rain_height > 0:
            grid[:] = new_grid
        else:
            grid[:] = []
        return render_frame()

    grid: list[list[str]] = []
    for _ in range(start_frame):
        step_frame()

    if paused:
        frozen = step_frame()
        while True:
            yield frozen

    while True:
        yield step_frame()
