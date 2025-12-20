"""Configuration persistence for RhythmSlicer."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class AppConfig:
    last_open_path: Optional[str] = None
    open_recursive: bool = False
    volume: int = 100
    repeat_mode: str = "off"
    shuffle: bool = False


def get_config_dir(app_name: str = "rhythm-slicer") -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA")
        if base:
            root = Path(base)
        else:
            root = Path.home() / "AppData" / "Roaming"
        return _ensure_dir(root / app_name)
    if os.name == "posix" and _is_macos():
        return _ensure_dir(Path.home() / "Library" / "Application Support" / app_name)
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return _ensure_dir(root / app_name)


def load_config() -> AppConfig:
    path = get_config_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return AppConfig()
    if not isinstance(raw, dict):
        return AppConfig()
    return _config_from_mapping(raw)


def save_config(cfg: AppConfig) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    data = {
        "last_open_path": cfg.last_open_path,
        "open_recursive": cfg.open_recursive,
        "volume": cfg.volume,
        "repeat_mode": cfg.repeat_mode,
        "shuffle": cfg.shuffle,
    }
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def _ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_macos() -> bool:
    return os.uname().sysname == "Darwin" if hasattr(os, "uname") else False


def _config_from_mapping(raw: dict[str, Any]) -> AppConfig:
    repeat = raw.get("repeat_mode", "off")
    if repeat not in {"off", "one", "all"}:
        repeat = "off"
    volume = raw.get("volume", 100)
    if not isinstance(volume, int):
        volume = 100
    volume = max(0, min(100, volume))
    last_open_path = raw.get("last_open_path")
    if last_open_path is not None and not isinstance(last_open_path, str):
        last_open_path = None
    open_recursive = raw.get("open_recursive", False)
    if not isinstance(open_recursive, bool):
        open_recursive = False
    shuffle = raw.get("shuffle", False)
    if not isinstance(shuffle, bool):
        shuffle = False
    return AppConfig(
        last_open_path=last_open_path,
        open_recursive=open_recursive,
        volume=volume,
        repeat_mode=repeat,
        shuffle=shuffle,
    )
