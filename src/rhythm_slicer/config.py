"""Configuration persistence for RhythmSlicer."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppConfig:
    """Immutable user configuration loaded from disk."""

    last_open_path: Optional[str] = None
    open_recursive: bool = False
    volume: int = 100
    repeat_mode: str = "off"
    shuffle: bool = False
    viz_name: str = "hackscope"
    ansi_colors: bool = True


def get_config_dir(app_name: str = "rhythm-slicer") -> Path:
    """Return the per-user config directory for the current platform."""
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            root = Path(base)
        else:
            root = Path.home() / "AppData" / "Roaming"
        return _ensure_dir(root / app_name)
    elif os.name == "posix":
        if _is_macos():
            return _ensure_dir(
                Path.home() / "Library" / "Application Support" / app_name
            )
        base = os.environ.get("XDG_CONFIG_HOME")
        root = Path(base) if base else Path.home() / ".config"
        return _ensure_dir(root / app_name)
    else:
        return _ensure_dir(Path.home() / ".config" / app_name)


def load_config() -> AppConfig:
    """Load configuration from disk, falling back to defaults on error."""
    path = get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load config from %s", path)
        return AppConfig()
    if not isinstance(raw, dict):
        return AppConfig()
    return _config_from_mapping(raw)


def save_config(cfg: AppConfig) -> None:
    """Persist configuration to disk atomically."""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    data = {
        "last_open_path": cfg.last_open_path,
        "open_recursive": cfg.open_recursive,
        "volume": cfg.volume,
        "repeat_mode": cfg.repeat_mode,
        "shuffle": cfg.shuffle,
        "viz_name": cfg.viz_name,
        "ansi_colors": cfg.ansi_colors,
    }
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def get_config_path() -> Path:
    """Return the full config file path."""
    return get_config_dir() / "config.json"


def _ensure_dir(path: Path) -> Path:
    """Create the directory if needed and return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_macos() -> bool:
    """Return True when running on macOS."""
    return os.uname().sysname == "Darwin" if hasattr(os, "uname") else False # pyright: ignore[reportAttributeAccessIssue]


def _get_bool(
    raw: dict[str, Any],
    key: str,
    default: bool,
    *,
    invalid_default: bool | None = None,
) -> bool:
    """Fetch a boolean value with fallback for invalid types."""
    value = raw.get(key, default)
    if isinstance(value, bool):
        return value
    if invalid_default is None:
        return default
    return invalid_default


def _get_int(
    raw: dict[str, Any],
    key: str,
    default: int,
    *,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int:
    """Fetch an integer value with optional clamping."""
    value = raw.get(key, default)
    if not isinstance(value, int):
        value = default
    if min_value is not None:
        value = max(min_value, value)
    if max_value is not None:
        value = min(max_value, value)
    return value


def _get_str(
    raw: dict[str, Any],
    key: str,
    default: str,
    *,
    allow_empty: bool = False,
) -> str:
    """Fetch a string value, optionally allowing empty strings."""
    value = raw.get(key, default)
    if not isinstance(value, str):
        return default
    if not value and not allow_empty:
        return default
    return value


def _config_from_mapping(raw: dict[str, Any]) -> AppConfig:
    """Normalize raw JSON data into an AppConfig."""
    repeat = raw.get("repeat_mode", "off")
    if repeat not in {"off", "one", "all"}:
        repeat = "off"
    volume = _get_int(raw, "volume", 100, min_value=0, max_value=100)
    last_open_path = raw.get("last_open_path")
    if last_open_path is not None and not isinstance(last_open_path, str):
        last_open_path = None
    open_recursive = _get_bool(raw, "open_recursive", False)
    shuffle = _get_bool(raw, "shuffle", False)
    viz_name = _get_str(raw, "viz_name", "hackscope")
    ansi_colors = _get_bool(raw, "ansi_colors", True, invalid_default=False)
    return AppConfig(
        last_open_path=last_open_path,
        open_recursive=open_recursive,
        volume=volume,
        repeat_mode=repeat,
        shuffle=shuffle,
        viz_name=viz_name,
        ansi_colors=ansi_colors,
    )
