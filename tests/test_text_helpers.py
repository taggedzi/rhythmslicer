from __future__ import annotations

from rhythm_slicer.ui.text_helpers import _truncate_line


def test_truncate_line_no_limit() -> None:
    assert _truncate_line("hello", 0) == ""
    assert _truncate_line("hello", -1) == ""


def test_truncate_line_no_truncation() -> None:
    assert _truncate_line("hello", 10) == "hello"


def test_truncate_line_small_width() -> None:
    assert _truncate_line("hello", 1) == "h"


def test_truncate_line_with_ellipsis() -> None:
    assert _truncate_line("hello", 4) == "hel…"
