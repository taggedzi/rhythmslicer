"""Prompt result encoding helpers."""

from __future__ import annotations


def _parse_prompt_result(value: str) -> tuple[str, bool]:
    if "::abs=" not in value:
        return value, False
    path, raw = value.rsplit("::abs=", 1)
    return path, raw.strip() == "1"


def _format_open_prompt_result(path: str, recursive: bool) -> str:
    return f"{path}::recursive={int(recursive)}"


def _parse_open_prompt_result(value: str) -> tuple[str, bool]:
    if "::recursive=" not in value:
        return value, False
    path, raw = value.rsplit("::recursive=", 1)
    return path, raw.strip() == "1"
