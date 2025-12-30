from __future__ import annotations

from dataclasses import dataclass

import pytest
from rich.text import Text

from rhythm_slicer.ui.status_panel import (
    StatusPanelCache,
    StatusPanelWidgets,
    update_status_panel,
)


class _FakeWidget:
    def __init__(self) -> None:
        self.calls: list[object] = []

    def update(self, content: object) -> None:
        self.calls.append(content)


@dataclass
class _Message:
    text: str
    level: str | None = None


def _make_widgets() -> StatusPanelWidgets:
    return StatusPanelWidgets(
        time_bar=_FakeWidget(),
        time_text=_FakeWidget(),
        volume_bar=_FakeWidget(),
        volume_text=_FakeWidget(),
        speed_bar=_FakeWidget(),
        speed_text=_FakeWidget(),
        state_text=_FakeWidget(),
    )


def _make_cache(**overrides: object) -> StatusPanelCache:
    base = dict(
        last_time_text=None,
        last_time_value=None,
        last_time_bar_text=None,
        last_volume_text=None,
        last_volume_value=None,
        last_volume_bar_text=None,
        last_speed_text=None,
        last_speed_value=None,
        last_speed_bar_text=None,
        last_state_text=None,
        last_message_level=None,
    )
    base.update(overrides)
    return StatusPanelCache(**base)


def test_time_text_update_without_bar_change() -> None:
    widgets = _make_widgets()
    cache = _make_cache(
        last_time_text="00:59 / 05:00",
        last_time_value=50,
        last_volume_text=" 30",
        last_volume_value=30,
        last_speed_text="1.00x",
        last_speed_value=1.0,
        last_state_text="STATE",
    )
    calls = {"format": 0, "bar_width": 0, "render_bar": 0}

    def format_status_time() -> tuple[str, int]:
        calls["format"] += 1
        return ("01:00 / 05:00", 50)

    def bar_widget_width(_widget: object) -> int:
        calls["bar_width"] += 1
        return 10

    def render_status_bar(width: int, ratio: float) -> str:
        calls["render_bar"] += 1
        return f"{width}:{ratio}"

    update_status_panel(
        widgets=widgets,
        cache=cache,
        force=False,
        format_status_time=format_status_time,
        volume=30,
        playback_rate=1.0,
        bar_widget_width=bar_widget_width,
        render_status_bar=render_status_bar,
        status_state_label=lambda: "STATE",
        current_message=lambda: None,
    )

    assert widgets.time_text.calls == ["01:00 / 05:00"]
    assert widgets.time_bar.calls == []
    assert calls == {"format": 1, "bar_width": 0, "render_bar": 0}


def test_time_bar_cache_skips_duplicate_bar_text() -> None:
    widgets = _make_widgets()
    cache = _make_cache(
        last_time_text="01:00 / 05:00",
        last_time_value=10,
        last_time_bar_text="BAR",
        last_volume_text=" 30",
        last_volume_value=30,
        last_speed_text="1.00x",
        last_speed_value=1.0,
        last_state_text="STATE",
    )
    calls = {"bar_width": 0, "render_bar": 0}

    def format_status_time() -> tuple[str, int]:
        return ("01:00 / 05:00", 20)

    def bar_widget_width(_widget: object) -> int:
        calls["bar_width"] += 1
        return 10

    def render_status_bar(width: int, ratio: float) -> str:
        calls["render_bar"] += 1
        return "BAR"

    update_status_panel(
        widgets=widgets,
        cache=cache,
        force=False,
        format_status_time=format_status_time,
        volume=30,
        playback_rate=1.0,
        bar_widget_width=bar_widget_width,
        render_status_bar=render_status_bar,
        status_state_label=lambda: "STATE",
        current_message=lambda: None,
    )

    assert widgets.time_bar.calls == []
    assert calls == {"bar_width": 1, "render_bar": 1}


def test_force_updates_all_widgets() -> None:
    widgets = _make_widgets()
    cache = _make_cache(
        last_time_text="01:00 / 05:00",
        last_time_value=20,
        last_time_bar_text="[==]",
        last_volume_text=" 30",
        last_volume_value=30,
        last_volume_bar_text="[==]",
        last_speed_text="1.00x",
        last_speed_value=1.0,
        last_speed_bar_text="[==]",
        last_state_text="STATE",
    )
    calls = {"bar_width": 0, "render_bar": 0}

    def format_status_time() -> tuple[str, int]:
        return ("01:00 / 05:00", 20)

    def bar_widget_width(_widget: object) -> int:
        calls["bar_width"] += 1
        return 4

    def render_status_bar(width: int, ratio: float) -> str:
        calls["render_bar"] += 1
        return "[==]"

    update_status_panel(
        widgets=widgets,
        cache=cache,
        force=True,
        format_status_time=format_status_time,
        volume=30,
        playback_rate=1.0,
        bar_widget_width=bar_widget_width,
        render_status_bar=render_status_bar,
        status_state_label=lambda: "STATE",
        current_message=lambda: None,
    )

    assert all(len(widget.calls) == 1 for widget in widgets.__dict__.values())
    assert calls == {"bar_width": 3, "render_bar": 3}


@pytest.mark.parametrize(
    ("volume", "expected_text", "expected_ratio"),
    [(-5, "  0", 0.0), (150, "100", 1.0)],
)
def test_volume_clamping(
    volume: int, expected_text: str, expected_ratio: float
) -> None:
    widgets = _make_widgets()
    cache = _make_cache(
        last_time_text="--:-- / --:--",
        last_time_value=0,
        last_volume_text=None,
        last_volume_value=None,
        last_speed_text="1.00x",
        last_speed_value=1.0,
        last_state_text="STATE",
    )
    seen: dict[str, float] = {}

    def format_status_time() -> tuple[str, int]:
        return ("--:-- / --:--", 0)

    def bar_widget_width(_widget: object) -> int:
        return 10

    def render_status_bar(width: int, ratio: float) -> str:
        seen["ratio"] = ratio
        return "BAR"

    update_status_panel(
        widgets=widgets,
        cache=cache,
        force=False,
        format_status_time=format_status_time,
        volume=volume,
        playback_rate=1.0,
        bar_widget_width=bar_widget_width,
        render_status_bar=render_status_bar,
        status_state_label=lambda: "STATE",
        current_message=lambda: None,
    )

    assert widgets.volume_text.calls == [expected_text]
    assert seen["ratio"] == expected_ratio


@pytest.mark.parametrize(
    ("rate", "expected_ratio"),
    [(0.5, 0.0), (2.25, 0.5), (4.0, 1.0)],
)
def test_speed_bar_ratio(rate: float, expected_ratio: float) -> None:
    widgets = _make_widgets()
    cache = _make_cache(
        last_time_text="--:-- / --:--",
        last_time_value=0,
        last_volume_text=" 30",
        last_volume_value=30,
        last_speed_text=None,
        last_speed_value=None,
        last_state_text="STATE",
    )
    seen: dict[str, float] = {}

    def format_status_time() -> tuple[str, int]:
        return ("--:-- / --:--", 0)

    def bar_widget_width(_widget: object) -> int:
        return 12

    def render_status_bar(width: int, ratio: float) -> str:
        seen["ratio"] = ratio
        return "SPEED"

    update_status_panel(
        widgets=widgets,
        cache=cache,
        force=False,
        format_status_time=format_status_time,
        volume=30,
        playback_rate=rate,
        bar_widget_width=bar_widget_width,
        render_status_bar=render_status_bar,
        status_state_label=lambda: "STATE",
        current_message=lambda: None,
    )

    assert seen["ratio"] == expected_ratio


@pytest.mark.parametrize(
    "text",
    ["playing", " PaUsEd ", "STOPPED", " loading", "loading...  "],
)
def test_message_normalization_clears_state_message(text: str) -> None:
    widgets = _make_widgets()
    cache = _make_cache(last_state_text="OLD", last_message_level=None)

    def format_status_time() -> tuple[str, int]:
        return ("--:-- / --:--", 0)

    update_status_panel(
        widgets=widgets,
        cache=cache,
        force=False,
        format_status_time=format_status_time,
        volume=30,
        playback_rate=1.0,
        bar_widget_width=lambda _widget: 4,
        render_status_bar=lambda width, ratio: "BAR",
        status_state_label=lambda: "STATE",
        current_message=lambda: _Message(text=text, level="warn"),
    )

    assert widgets.state_text.calls[-1] == "STATE"
    assert cache.last_message_level is None
    assert cache.last_state_text == "STATE"


def test_warn_message_uses_text_and_preserves_cache() -> None:
    widgets = _make_widgets()
    cache = _make_cache(last_state_text="OLD", last_message_level=None)

    def format_status_time() -> tuple[str, int]:
        return ("--:-- / --:--", 0)

    update_status_panel(
        widgets=widgets,
        cache=cache,
        force=False,
        format_status_time=format_status_time,
        volume=30,
        playback_rate=1.0,
        bar_widget_width=lambda _widget: 4,
        render_status_bar=lambda width, ratio: "BAR",
        status_state_label=lambda: "STATE",
        current_message=lambda: _Message(text="Heads up", level="warn"),
    )

    assert isinstance(widgets.state_text.calls[-1], Text)
    assert cache.last_state_text == "OLD"
    assert cache.last_message_level == "warn"
