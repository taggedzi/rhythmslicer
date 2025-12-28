"""Utilities for visualizer text rendering."""

from __future__ import annotations

from rhythm_slicer.ui.tui_formatters import _truncate_line


def tiny_visualizer_text(width: int, height: int) -> str:
    message = "Visualizer too small"
    line = _truncate_line(message, width).ljust(width)
    lines = [line] + [" " * width for _ in range(max(0, height - 1))]
    return "\n".join(lines)


def clip_frame_text(text: str, width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return ""
    lines = text.splitlines()
    if not lines:
        lines = [""]
    clipped: list[str] = []
    for idx in range(height):
        line = lines[idx] if idx < len(lines) else ""
        if len(line) > width:
            line = line[:width]
        clipped.append(line.ljust(width))
    return "\n".join(clipped)


def center_visualizer_message(message: str, width: int, height: int) -> str:
    line = _truncate_line(message, width)
    pad = max(0, (width - len(line)) // 2)
    centered = (" " * pad + line).ljust(width)
    top_pad = max(0, (height - 1) // 2)
    lines = [" " * width for _ in range(top_pad)]
    lines.append(centered)
    lines.extend([" " * width for _ in range(max(0, height - len(lines)))])
    return "\n".join(lines[:height])


def visualizer_hud_size(visualizer_hud: object | None) -> tuple[int, int]:
    if not visualizer_hud:
        return (1, 1)
    size = getattr(visualizer_hud, "content_size", None) or getattr(
        visualizer_hud, "size"
    )
    width = max(1, getattr(size, "width", 1))
    height = max(1, getattr(size, "height", 1))
    return (width, height)
