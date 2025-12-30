from __future__ import annotations

from rich.text import Text

from rhythm_slicer.ui.status_controller import StatusController


class _Node:
    def __init__(self, node_id: str, parent: "_Node | None" = None) -> None:
        self.id = node_id
        self.parent = parent


def test_show_message_default_timeouts() -> None:
    controller = StatusController(now=lambda: 10.0)
    controller.show_message("Warn", level="warn")
    assert controller._message is not None
    assert controller._message.until == 16.0
    controller.show_message("Error", level="error")
    assert controller._message is not None
    assert controller._message.until == 16.0
    controller.show_message("Info", level="info")
    assert controller._message is not None
    assert controller._message.until == 13.0


def test_show_message_timeout_zero_persists() -> None:
    controller = StatusController(now=lambda: 0.0)
    controller.show_message("Hello", timeout=0)
    assert controller._message is not None
    assert controller._message.until is None
    assert "Hello" in controller.render_line(80).plain


def test_render_line_applies_styles() -> None:
    controller = StatusController(now=lambda: 0.0)
    controller.show_message("Warn", level="warn", timeout=5.0)
    line = controller.render_line(40)
    assert isinstance(line, Text)
    assert line.plain == "Warn"
    assert line.style == "#ffcc66"
    controller.show_message("Error", level="error", timeout=5.0)
    line = controller.render_line(40)
    assert line.style == "#ff5f52"


def test_message_expiration_falls_back_to_hint() -> None:
    now_value = [0.0]
    controller = StatusController(now=lambda: now_value[0])
    controller.show_message("Hello", timeout=1.0)
    assert "Hello" in controller.render_line(80).plain
    now_value[0] = 2.0
    line = controller.render_line(80).plain
    assert "Hello" not in line
    assert "Space: play/pause" in line


def test_clear_message_resets_state() -> None:
    controller = StatusController(now=lambda: 0.0)
    controller.show_message("Hello", timeout=5.0)
    controller.clear_message()
    assert controller._message is None


def test_render_hint_from_focus_and_context() -> None:
    controller = StatusController(now=lambda: 0.0)
    line = controller.render_line(80, focused="playlist_list").plain
    assert "Enter: play" in line
    line = controller.render_line(80, focused="visualizer").plain
    assert "change viz" in line
    line = controller.render_line(80, focused="transport_row").plain
    assert "Space: play/pause" in line
    controller.set_context("playlist")
    assert "Enter: play" in controller.render_line(80).plain


def test_context_from_focus_parent_chain() -> None:
    controller = StatusController(now=lambda: 0.0)
    parent = _Node("transport_row")
    child = _Node("child", parent=parent)
    line = controller.render_line(80, focused=child).plain
    assert "Space: play/pause" in line


def test_context_from_focus_general_default() -> None:
    controller = StatusController(now=lambda: 0.0)
    line = controller.render_line(80, focused="unknown").plain
    assert "Space: play/pause" in line


def test_context_from_focus_object_default() -> None:
    controller = StatusController(now=lambda: 0.0)
    obj = _Node("unknown")
    line = controller.render_line(80, focused=obj).plain
    assert "Space: play/pause" in line
