from __future__ import annotations

from rhythm_slicer.ui.prompt_codec import (
    _format_open_prompt_result,
    _parse_open_prompt_result,
    _parse_prompt_result,
)


def test_parse_prompt_result_without_marker() -> None:
    assert _parse_prompt_result("path/to/file") == ("path/to/file", False)


def test_parse_prompt_result_with_marker() -> None:
    assert _parse_prompt_result("path/to/file::abs=1") == ("path/to/file", True)
    assert _parse_prompt_result("path/to/file::abs=0") == ("path/to/file", False)


def test_parse_prompt_result_trims_raw() -> None:
    assert _parse_prompt_result("path/to/file::abs= 1 ") == ("path/to/file", True)


def test_format_open_prompt_result_round_trip() -> None:
    encoded = _format_open_prompt_result("/tmp/music", True)
    assert encoded == "/tmp/music::recursive=1"
    assert _parse_open_prompt_result(encoded) == ("/tmp/music", True)


def test_parse_open_prompt_result_without_marker() -> None:
    assert _parse_open_prompt_result("/tmp/music") == ("/tmp/music", False)
