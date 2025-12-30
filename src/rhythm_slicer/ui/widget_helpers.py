from __future__ import annotations

from typing import Any


def bar_widget_width(widget: Any) -> int:
    size = getattr(widget, "content_size", None) or widget.size
    return max(1, getattr(size, "width", 1))
