"""Status panel updates for the TUI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from rich.text import Text


class Updatable(Protocol):
    def update(self, content: Any) -> None:
        ...


@dataclass
class StatusPanelWidgets:
    time_bar: Updatable
    time_text: Updatable
    volume_bar: Updatable
    volume_text: Updatable
    speed_bar: Updatable
    speed_text: Updatable
    state_text: Updatable


@dataclass
class StatusPanelCache:
    last_time_text: str | None
    last_time_value: int | None
    last_time_bar_text: str | None
    last_volume_text: str | None
    last_volume_value: int | None
    last_volume_bar_text: str | None
    last_speed_text: str | None
    last_speed_value: float | None
    last_speed_bar_text: str | None
    last_state_text: str | None
    last_message_level: str | None


def update_status_panel(
    *,
    widgets: StatusPanelWidgets,
    cache: StatusPanelCache,
    force: bool,
    format_status_time: Callable[[], tuple[str, int]],
    volume: int,
    playback_rate: float,
    bar_widget_width: Callable[[Any], int],
    render_status_bar: Callable[[int, float], str],
    status_state_label: Callable[[], str],
    current_message: Callable[[], Any | None],
) -> None:
    time_text, time_value = format_status_time()
    if force or time_text != cache.last_time_text:
        widgets.time_text.update(time_text)
        cache.last_time_text = time_text
    if force or time_value != cache.last_time_value:
        bar_width = bar_widget_width(widgets.time_bar)
        bar_text = render_status_bar(bar_width, time_value / 100.0)
        if force or bar_text != cache.last_time_bar_text:
            widgets.time_bar.update(bar_text)
            cache.last_time_bar_text = bar_text
        cache.last_time_value = time_value

    volume_value = max(0, min(volume, 100))
    volume_text = f"{volume_value:3d}"
    if force or volume_text != cache.last_volume_text:
        widgets.volume_text.update(volume_text)
        cache.last_volume_text = volume_text
    if force or volume_value != cache.last_volume_value:
        bar_width = bar_widget_width(widgets.volume_bar)
        bar_text = render_status_bar(bar_width, volume_value / 100.0)
        if force or bar_text != cache.last_volume_bar_text:
            widgets.volume_bar.update(bar_text)
            cache.last_volume_bar_text = bar_text
        cache.last_volume_value = volume_value

    speed_value = playback_rate
    speed_text = f"{speed_value:0.2f}x"
    if force or speed_text != cache.last_speed_text:
        widgets.speed_text.update(speed_text)
        cache.last_speed_text = speed_text
    if force or speed_value != cache.last_speed_value:
        bar_width = bar_widget_width(widgets.speed_bar)
        ratio = (speed_value - 0.5) / (4.0 - 0.5)
        bar_text = render_status_bar(bar_width, ratio)
        if force or bar_text != cache.last_speed_bar_text:
            widgets.speed_bar.update(bar_text)
            cache.last_speed_bar_text = bar_text
        cache.last_speed_value = speed_value

    message = current_message()
    message_text = message.text.splitlines()[0] if message else ""
    message_level = message.level if message else None
    normalized = message_text.strip().lower()
    if normalized in {"playing", "paused", "stopped", "loading", "loading..."}:
        message_text = ""
        message_level = None
    state_text = status_state_label()
    display_text = (
        f"{state_text} {message_text}" if message_text else state_text
    ).rstrip()
    if (
        force
        or display_text != cache.last_state_text
        or message_level != cache.last_message_level
    ):
        style = None
        if message_level == "warn":
            style = "#ffcc66"
        elif message_level == "error":
            style = "#ff5f52"
        if message_text and style:
            text = Text(state_text)
            text.append(" ")
            text.append(message_text, style=style)
            widgets.state_text.update(text)
        else:
            widgets.state_text.update(display_text)
            cache.last_state_text = display_text
        cache.last_message_level = message_level
