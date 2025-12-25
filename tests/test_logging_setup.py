"""Tests for logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from rhythm_slicer import logging_setup


def test_default_log_dir_uses_local_appdata(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    log_dir = logging_setup._default_log_dir()
    assert log_dir == tmp_path / "RhythmSlicer" / "logs"


def test_default_log_dir_falls_back_to_home(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(logging_setup.Path, "home", lambda: tmp_path)
    log_dir = logging_setup._default_log_dir()
    assert log_dir == tmp_path / ".rhythm_slicer" / "logs"


def test_init_logging_creates_handlers(monkeypatch, tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logging_setup, "_default_log_dir", lambda: log_dir)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    root.handlers.clear()
    try:
        log_path = logging_setup.init_logging()
        assert log_path == log_dir / "app.log"
        assert any(isinstance(h, logging.Handler) for h in root.handlers)
    finally:
        root.handlers = original_handlers


def test_init_logging_invalid_level_defaults(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("RHYTHMSLICER_LOG_LEVEL", "notalevel")
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(logging_setup, "_default_log_dir", lambda: log_dir)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    root.handlers.clear()
    try:
        logging_setup.init_logging()
        assert root.level == logging.INFO
    finally:
        root.handlers = original_handlers


def test_set_console_level_adjusts_stream_only(tmp_path: Path) -> None:
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    root.handlers.clear()
    try:
        stream_handler = logging.StreamHandler()
        file_handler = logging.FileHandler(tmp_path / "app.log")
        stream_handler.setLevel(logging.INFO)
        file_handler.setLevel(logging.INFO)
        root.addHandler(stream_handler)
        root.addHandler(file_handler)
        logging_setup.set_console_level(logging.ERROR)
        assert stream_handler.level == logging.ERROR
        assert file_handler.level == logging.INFO
    finally:
        root.handlers = original_handlers
