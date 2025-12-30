from __future__ import annotations

from rhythm_slicer.ui.marquee import Marquee


def test_marquee_scrolls_long_text() -> None:
    marquee = Marquee(step_interval=0.1, start_pause=0.0, loop_pause=0.0)
    marquee.set_width_override(10)
    marquee.set_text("abcdefghijklmnopqrstuvwxyz")
    first = marquee.current_text
    marquee._tick()
    second = marquee.current_text
    assert first != second


def test_marquee_does_not_scroll_short_text() -> None:
    marquee = Marquee(step_interval=0.1, start_pause=0.0, loop_pause=0.0)
    marquee.set_width_override(10)
    marquee.set_text("short")
    first = marquee.current_text
    marquee._tick()
    second = marquee.current_text
    assert first == "short"
    assert second == "short"
