"""Logging setup for RhythmSlicer."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


def _default_log_dir() -> Path:
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "RhythmSlicer" / "logs"
    return Path.home() / ".rhythm_slicer" / "logs"


def init_logging(app_name: str = "rhythm_slicer") -> Path:
    """Initialize logging and return the log file path."""
    log_dir = _default_log_dir()
    log_path = log_dir / "app.log"
    level_name = os.getenv("RHYTHMSLICER_LOG_LEVEL", "INFO").upper()
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        level = logging.INFO

    logger = logging.getLogger()
    logger.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
    )

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)

        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)

        if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
            logger.addHandler(file_handler)
        if not any(
            isinstance(h, logging.StreamHandler)
            and not isinstance(h, logging.FileHandler)
            for h in logger.handlers
        ):
            logger.addHandler(stream_handler)
    except Exception:
        logging.basicConfig(level=level, format=str(formatter._fmt))

    logging.getLogger(app_name).info("Logging initialized at %s", log_path)
    return log_path


def set_console_level(level: int) -> None:
    """Adjust console (stderr) handler level."""
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(
            handler, logging.FileHandler
        ):
            handler.setLevel(level)
