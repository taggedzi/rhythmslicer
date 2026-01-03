from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from typing_extensions import TypeAlias

TrackSignature: TypeAlias = tuple[Optional[int], str, str, str, int, int]


@dataclass
class StatusMessage:
    text: str
    level: str
    until: Optional[float]
