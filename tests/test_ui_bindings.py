from __future__ import annotations

from textual.binding import Binding

from rhythm_slicer.ui.bindings import normalize_bindings


def test_normalize_bindings_keeps_binding_instances() -> None:
    binding = Binding("a", "action-a", "Action A")
    result = normalize_bindings([binding])
    assert result == [binding]


def test_normalize_bindings_converts_tuples() -> None:
    result = normalize_bindings([("b", "action-b", "Action B")])
    assert isinstance(result[0], Binding)
    assert result[0].key == "b"
    assert result[0].action == "action-b"
    assert result[0].description == "Action B"
