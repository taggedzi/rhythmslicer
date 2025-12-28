"""Utilities for visualizer text rendering."""

from __future__ import annotations

from typing import Any, Callable
from pathlib import Path

from rich.text import Text

from rhythm_slicer.metadata import TrackMeta
from rhythm_slicer.playlist import Playlist, Track
from rhythm_slicer.ui.text_helpers import _truncate_line


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


def render_ansi_frame(text: str, width: int, height: int) -> Text:
    lines = text.splitlines()
    if not lines:
        lines = [""]
    rendered = Text()
    for idx in range(height):
        if idx > 0:
            rendered.append("\n")
        line = lines[idx] if idx < len(lines) else ""
        line_text = Text.from_ansi(line)
        if line_text.cell_len > width:
            line_text.truncate(width)
        if line_text.cell_len < width:
            line_text.append(" " * (width - line_text.cell_len))
        rendered.append_text(line_text)
    return rendered


def render_visualizer_view(
    *,
    width: int,
    height: int,
    mode: str,
    frame_player_is_running: bool,
    seed_ms: int,
    bars_fn: Callable[[int, int, int], Any],
    render_bars_fn: Callable[[Any, int], str],
    render_mode_fn: Callable[[str, int, int], str],
    tiny_text_fn: Callable[[int, int], str],
) -> str:
    if width <= 0 or height <= 0:
        return ""
    if width <= 2 or height <= 1:
        return tiny_text_fn(width, height)
    if mode == "PLAYING" and not frame_player_is_running:
        bars = bars_fn(seed_ms, width, height)
        return render_bars_fn(bars, height)
    return render_mode_fn(mode, width, height)


def render_visualizer_mode(
    mode: str,
    width: int,
    height: int,
    *,
    now: Callable[[], float],
    loading_step: float,
    tiny_text_fn: Callable[[int, int], str],
    center_message_fn: Callable[[str, int, int], str],
) -> str:
    if width <= 0 or height <= 0:
        return ""
    if width <= 2 or height <= 1:
        return tiny_text_fn(width, height)
    message = mode
    if mode == "LOADING":
        phase = int(now() / loading_step) % 4
        message = f"LOADING{'.' * phase}"
    return center_message_fn(message, width, height)


def render_visualizer_hud(
    *,
    width: int,
    height: int,
    playlist: Playlist | None,
    playing_index: int | None,
    get_meta_cached: Callable[[Path], TrackMeta | None],
    ensure_meta_loaded: Callable[[Path], None],
    ellipsize_fn: Callable[[str, int], str],
) -> Text:
    if width <= 0 or height <= 0:
        return Text("")
    track: Track | None = None
    if playlist and playing_index is not None:
        if 0 <= playing_index < len(playlist.tracks):
            track = playlist.tracks[playing_index]
    meta = get_meta_cached(track.path) if track else None
    if track and meta is None:
        ensure_meta_loaded(track.path)
    title = meta.title if meta and meta.title else (track.title if track else "—")
    if not title and track:
        title = track.path.name
    artist = meta.artist if meta and meta.artist else "Unknown"
    album = meta.album if meta and meta.album else "Unknown"

    label_style = "dim"
    value_style = "#c6d0f2"
    title_style = "bold #5fc9d6"

    def column_text(
        label: str, value: str, col_width: int, *, is_title: bool = False
    ) -> Text:
        label_text = f"{label}: "
        value_width = max(1, col_width - len(label_text))
        value_text = ellipsize_fn(value, value_width)
        text = Text(label_text, style=label_style)
        style = title_style if is_title else value_style
        text.append(value_text, style=style)
        if text.cell_len < col_width:
            text.append(" " * (col_width - text.cell_len))
        return text

    lines: list[Text] = []
    lines.append(column_text("TITLE", title, width, is_title=True))
    lines.append(column_text("ARTIST", artist, width))
    lines.append(column_text("ALBUM", album, width))

    if len(lines) < height:
        lines.extend([Text(" " * width)] * (height - len(lines)))
    if len(lines) > height:
        lines = lines[:height]
    output = Text()
    for idx, line in enumerate(lines):
        if idx:
            output.append("\n")
        output.append_text(line)
    return output
