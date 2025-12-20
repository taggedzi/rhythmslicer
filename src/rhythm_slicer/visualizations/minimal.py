"""Minimal built-in visualization plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from rhythm_slicer.visualizations.host import VizContext

VIZ_NAME = "minimal"

_SPINNER = ("|", "/", "-", "\\")


def _format_lines(lines: list[str], width: int, height: int) -> str:
    width = max(1, width)
    height = max(1, height)
    padded: list[str] = []
    for idx in range(height):
        line = lines[idx] if idx < len(lines) else ""
        if len(line) > width:
            line = line[:width]
        padded.append(line.ljust(width))
    return "\n".join(padded)


def _line_two(ctx: VizContext) -> str:
    base = Path(ctx.track_path).name if ctx.track_path else "Unknown"
    title = ctx.meta.get("title") if isinstance(ctx.meta, dict) else None
    artist = ctx.meta.get("artist") if isinstance(ctx.meta, dict) else None
    details: list[str] = []
    if artist:
        details.append(str(artist))
    if title:
        details.append(str(title))
    if details:
        return f"{base} | {' - '.join(details)}"
    return base


def generate_frames(ctx: VizContext) -> Iterator[str]:
    width = max(1, ctx.viewport_w)
    height = max(1, ctx.viewport_h)
    line_two = _line_two(ctx)
    index = 0
    while True:
        spin = _SPINNER[index % len(_SPINNER)]
        line_one = f"[RhythmSlicer] minimal viz {spin}"
        yield _format_lines([line_one, line_two], width, height)
        index += 1
