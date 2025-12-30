from __future__ import annotations

import pytest

from rhythm_slicer.ui.tui_formatters import (
    _display_state,
    _format_time_ms,
    ellipsize,
    format_status_time,
    playback_state_label,
    ratio_from_click,
    render_status_bar,
    render_visualizer,
    status_state_label,
    target_ms_from_ratio,
    visualizer_bars,
)


def test_render_status_bar_width_leq_zero() -> None:
    assert render_status_bar(0, 0.0) == ""
    assert render_status_bar(-2, 0.5) == ""


def test_render_status_bar_small_widths() -> None:
    assert render_status_bar(1, 0.0) == "█"
    assert render_status_bar(2, 0.0) == "[-]"
    assert render_status_bar(3, 0.0) == "[-]"


def test_render_status_bar_ratio_clamping() -> None:
    assert render_status_bar(4, -1.0) == "[--]"
    assert render_status_bar(4, 2.0) == "[==]"


def test_render_status_bar_length_matches_width_for_wide_bars() -> None:
    for width in (1, 3, 5):
        bar = render_status_bar(width, 0.5)
        assert len(bar) == width


@pytest.mark.parametrize(
    ("state", "loading", "expected"),
    [
        ("playing", False, "PLAYING"),
        ("PaUsEd", False, "PAUSED"),
        ("stop", False, "STOPPED"),
        ("", False, "STOPPED"),
        ("something", False, "STOPPED"),
        ("playing", True, "LOADING"),
    ],
)
def test_playback_state_label_variants(
    state: str, loading: bool, expected: str
) -> None:
    assert playback_state_label(playback_state=state, loading=loading) == expected


def test_status_state_label_formats_state() -> None:
    calls = {"label": 0}

    def playback_state() -> str:
        calls["label"] += 1
        return "PAUSED"

    label = status_state_label(
        playback_state_label=playback_state, shuffle=False, repeat_mode="off"
    )
    assert label == "[ PAUSED  ]"
    assert calls == {"label": 1}


def test_format_status_time_loading_short_circuits() -> None:
    calls = {"pos": 0, "len": 0}

    def get_position_ms() -> int | None:
        calls["pos"] += 1
        return 1000

    def get_length_ms() -> int | None:
        calls["len"] += 1
        return 5000

    assert format_status_time(
        loading=True,
        get_position_ms=get_position_ms,
        get_length_ms=get_length_ms,
    ) == ("--:-- / --:--", 0)
    assert calls == {"pos": 0, "len": 0}


def test_format_status_time_missing_position_or_length() -> None:
    assert format_status_time(
        loading=False, get_position_ms=lambda: None, get_length_ms=lambda: 5000
    ) == ("--:-- / --:--", 0)
    assert format_status_time(
        loading=False, get_position_ms=lambda: 1000, get_length_ms=lambda: None
    ) == ("--:-- / --:--", 0)


def test_format_status_time_progress_and_formatting() -> None:
    assert format_status_time(
        loading=False, get_position_ms=lambda: 61_000, get_length_ms=lambda: 300_000
    ) == ("01:01 / 05:00", 20)


def test_format_status_time_progress_clamped() -> None:
    assert format_status_time(
        loading=False,
        get_position_ms=lambda: 400_000,
        get_length_ms=lambda: 300_000,
    ) == ("06:40 / 05:00", 100)


def test_visualizer_bars_invalid_dimensions() -> None:
    assert visualizer_bars(seed_ms=1000, width=0, height=4) == []
    assert visualizer_bars(seed_ms=1000, width=4, height=-1) == []


def test_visualizer_bars_deterministic() -> None:
    assert visualizer_bars(seed_ms=1000, width=4, height=3) == [2, 2, 0, 0]


def test_render_visualizer_empty_or_zero() -> None:
    assert render_visualizer([], height=3) == ""
    assert render_visualizer([1, 2], height=0) == ""


def test_render_visualizer_output() -> None:
    assert render_visualizer([2, 2, 0, 0], height=3) == "    \n##  \n##  "


def test_format_time_ms_variants() -> None:
    assert _format_time_ms(None) is None
    assert _format_time_ms(-1) == "00:00"
    assert _format_time_ms(61_000) == "01:01"
    assert _format_time_ms(3_600_000) == "01:00:00"


def test_display_state() -> None:
    assert _display_state("playing") == "Playing"
    assert _display_state("") == "Unknown"


def test_ellipsize_edges() -> None:
    assert ellipsize("abc", 0) == ""
    assert ellipsize("abcdef", 2) == ".."
    assert ellipsize("abcdef", 3) == "..."
    assert ellipsize("abcdef", 4) == "a..."


def test_ratio_from_click_clamped() -> None:
    assert ratio_from_click(5, 1) == 0.0
    assert ratio_from_click(-1, 5) == 0.0
    assert ratio_from_click(4, 5) == 1.0


def test_target_ms_from_ratio_clamped() -> None:
    assert target_ms_from_ratio(1000, -1.0) == 0
    assert target_ms_from_ratio(1000, 2.0) == 1000
