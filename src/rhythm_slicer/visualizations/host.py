"""Visualization host types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator, Protocol


@dataclass(frozen=True)
class VizContext:
    track_path: str
    viewport_w: int
    viewport_h: int
    prefs: dict[str, Any]
    meta: dict[str, Any]
    seed: int | None = None


class VizPlugin(Protocol):
    VIZ_NAME: str

    def generate_frames(self, ctx: VizContext) -> Iterator[str]: ...
