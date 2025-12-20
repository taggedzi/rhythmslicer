"""ANSI sanitization helpers for visualization frames."""

from __future__ import annotations

import re

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_CSI_PATTERN = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_OSC_PATTERN = re.compile(r"\x1b\][^\x07]*(\x07|\x1b\\)")
_ESC_2CHAR_PATTERN = re.compile(r"\x1b[@-Z\\-_]")
_C1_CONTROL_PATTERN = re.compile(r"[\x80-\x9f]")


def sanitize_ansi_sgr(text: str) -> str:
    """Return text with only SGR ANSI sequences preserved."""
    if not text:
        return text
    placeholders: list[str] = []

    def _stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"__ANSI_SGR_{len(placeholders) - 1}__"

    cleaned = _SGR_PATTERN.sub(_stash, text)
    cleaned = _OSC_PATTERN.sub("", cleaned)
    cleaned = _CSI_PATTERN.sub("", cleaned)
    cleaned = _ESC_2CHAR_PATTERN.sub("", cleaned)
    cleaned = _C1_CONTROL_PATTERN.sub("", cleaned)
    for idx, seq in enumerate(placeholders):
        cleaned = cleaned.replace(f"__ANSI_SGR_{idx}__", seq)
    return cleaned
