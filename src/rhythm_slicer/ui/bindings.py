from __future__ import annotations

from typing import Any, Iterable, cast

from textual.binding import Binding


def normalize_bindings(source: Iterable[Binding | tuple[Any, ...]]) -> list[Binding]:
    bindings: list[Binding] = []
    for binding in source:
        if isinstance(binding, Binding):
            bindings.append(binding)
        else:
            bindings.append(Binding(*cast(tuple[Any, ...], binding)))
    return bindings
