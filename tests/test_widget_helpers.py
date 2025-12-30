from __future__ import annotations

from rhythm_slicer.ui.widget_helpers import bar_widget_width


class _Size:
    def __init__(self, width: int | None = None) -> None:
        if width is not None:
            self.width = width


class _Widget:
    def __init__(
        self, *, content_size: _Size | None = None, size: _Size | None = None
    ) -> None:
        if content_size is not None:
            self.content_size = content_size
        if size is not None:
            self.size = size


def test_bar_widget_width_prefers_content_size() -> None:
    widget = _Widget(content_size=_Size(10), size=_Size(4))
    assert bar_widget_width(widget) == 10


def test_bar_widget_width_falls_back_to_size() -> None:
    widget = _Widget(size=_Size(7))
    assert bar_widget_width(widget) == 7


def test_bar_widget_width_defaults_and_clamps() -> None:
    widget_missing = _Widget(size=_Size())
    assert bar_widget_width(widget_missing) == 1
    widget_zero = _Widget(size=_Size(0))
    assert bar_widget_width(widget_zero) == 1
