"""Tests for help modal formatting helpers."""

from __future__ import annotations

from textual.binding import Binding

from rhythm_slicer.ui import help_modal


def test_format_key_handles_special_cases() -> None:
    assert help_modal._format_key("left") == "←"
    assert help_modal._format_key("space") == "Space"
    assert help_modal._format_key("enter") == "Enter"
    assert help_modal._format_key("ctrl+x") == "Ctrl+X"


def test_build_help_text_includes_sections_and_overrides() -> None:
    bindings = [
        Binding("h", "show_help", "Help"),
        Binding("v", "select_visualization", "Viz"),
        Binding("q", "quit_app", "Quit"),
        Binding("d", "dump_threads", "Dump"),
    ]
    text = help_modal.build_help_text(bindings).plain
    assert "General" in text
    assert "Troubleshooting" in text
    assert "Change visualization" in text
    assert "Logs —" in text


def test_help_modal_dismiss_handlers() -> None:
    called: list[bool] = []

    class DummyButton:
        id = "help_close"

    class DummyPressed:
        button = DummyButton()

    class DummyKey:
        def __init__(self, key: str) -> None:
            self.key = key

    modal = help_modal.HelpModal([])
    modal.dismiss = lambda *_args, **_kwargs: called.append(True)  # type: ignore[assignment]
    modal.on_button_pressed(DummyPressed())
    assert called
    called.clear()
    modal.on_key(DummyKey("escape"))
    modal.on_key(DummyKey("q"))
    assert len(called) == 2
