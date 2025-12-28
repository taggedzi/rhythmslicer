from rhythm_slicer.ui.visualizer_rendering import (
    center_visualizer_message,
    clip_frame_text,
    tiny_visualizer_text,
    visualizer_hud_size,
)


class _Size:
    def __init__(self, width=None, height=None) -> None:
        if width is not None:
            self.width = width
        if height is not None:
            self.height = height


class _Hud:
    def __init__(self, *, content_size=None, size=None) -> None:
        if content_size is not None:
            self.content_size = content_size
        if size is not None:
            self.size = size


def test_clip_frame_text_non_positive_dimensions() -> None:
    assert clip_frame_text("abc", 0, 2) == ""
    assert clip_frame_text("abc", 2, 0) == ""
    assert clip_frame_text("abc", -1, 1) == ""


def test_clip_frame_text_empty_text() -> None:
    assert clip_frame_text("", 3, 2) == "   \n   "


def test_clip_frame_text_truncates_long_lines() -> None:
    assert clip_frame_text("abcdef", 4, 1) == "abcd"


def test_clip_frame_text_pads_missing_lines() -> None:
    assert clip_frame_text("a", 2, 3) == "a \n  \n  "


def test_tiny_visualizer_text_truncates_and_pads() -> None:
    assert tiny_visualizer_text(5, 2) == "Visu…\n     "


def test_tiny_visualizer_text_height_zero() -> None:
    assert tiny_visualizer_text(5, 0) == "Visu…"


def test_tiny_visualizer_text_line_widths() -> None:
    text = tiny_visualizer_text(4, 3)
    lines = text.split("\n")
    assert len(lines) == 3
    assert all(len(line) == 4 for line in lines)


def test_center_visualizer_message_centered() -> None:
    assert center_visualizer_message("abc", 7, 3) == "       \n  abc  \n       "


def test_center_visualizer_message_height_zero() -> None:
    assert center_visualizer_message("abc", 7, 0) == ""


def test_center_visualizer_message_width_zero() -> None:
    assert center_visualizer_message("abc", 0, 2) == "\n"


def test_center_visualizer_message_max_height() -> None:
    assert center_visualizer_message("abc", 5, 1) == " abc "


def test_visualizer_hud_size_none() -> None:
    assert visualizer_hud_size(None) == (1, 1)


def test_visualizer_hud_size_content_size_preferred() -> None:
    hud = _Hud(content_size=_Size(width=10, height=2), size=_Size(width=3, height=4))
    assert visualizer_hud_size(hud) == (10, 2)


def test_visualizer_hud_size_fallback_to_size() -> None:
    hud = _Hud(size=_Size(width=4, height=5))
    assert visualizer_hud_size(hud) == (4, 5)


def test_visualizer_hud_size_missing_dimensions_default() -> None:
    hud = _Hud(size=_Size())
    assert visualizer_hud_size(hud) == (1, 1)


def test_visualizer_hud_size_clamped_to_one() -> None:
    hud = _Hud(size=_Size(width=0, height=-2))
    assert visualizer_hud_size(hud) == (1, 1)
