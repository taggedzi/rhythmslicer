"""Tests for config persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path


from rhythm_slicer import config


def test_load_defaults_when_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    loaded = config.load_config()
    assert loaded == config.AppConfig()


def test_load_defaults_when_corrupt(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    config_path = tmp_path / "config.json"
    config_path.write_text("{not-json", encoding="utf-8")
    loaded = config.load_config()
    assert loaded == config.AppConfig()


def test_load_defaults_when_read_fails(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"

    def boom(*_args, **_kwargs) -> str:
        raise OSError("nope")

    monkeypatch.setattr(config, "get_config_path", lambda: config_path)
    monkeypatch.setattr(Path, "read_text", boom)
    loaded = config.load_config()
    assert loaded == config.AppConfig()


def test_save_load_round_trip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    original = config.AppConfig(
        last_open_path="/tmp/music",
        open_recursive=True,
        volume=75,
        repeat_mode="one",
        shuffle=True,
        viz_name="matrix",
        ansi_colors=True,
    )
    config.save_config(original)
    loaded = config.load_config()
    assert loaded == original


def test_save_config_atomic_write(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config, "get_config_dir", lambda: tmp_path)
    replaced: list[tuple[Path, Path]] = []

    def fake_replace(src: Path, dest: Path) -> None:
        replaced.append((src, dest))
        assert src.exists()
        data = json.loads(src.read_text(encoding="utf-8"))
        assert "volume" in data
        dest.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(config.os, "replace", fake_replace)
    config.save_config(config.AppConfig())
    assert replaced
    src, dest = replaced[0]
    assert src.suffix == ".tmp"
    assert dest.name == "config.json"


def test_config_from_mapping_sanitizes_values() -> None:
    raw = {
        "last_open_path": 123,
        "open_recursive": "nope",
        "volume": "loud",
        "repeat_mode": "bad",
        "shuffle": "yes",
        "viz_name": "",
        "ansi_colors": "maybe",
    }
    cfg = config._config_from_mapping(raw)
    assert cfg.last_open_path is None
    assert cfg.open_recursive is False
    assert cfg.volume == 100
    assert cfg.repeat_mode == "off"
    assert cfg.shuffle is False
    assert cfg.viz_name == "hackscope"
    assert cfg.ansi_colors is False


def test_get_config_dir_os_defaults(monkeypatch, tmp_path: Path) -> None:
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", str(tmp_path))
        path = config.get_config_dir("rhythm")
        assert path == tmp_path / "rhythm"
        monkeypatch.delenv("APPDATA", raising=False)
        monkeypatch.setattr(config.Path, "home", lambda: tmp_path)
        path = config.get_config_dir("rhythm")
        assert path == tmp_path / "AppData" / "Roaming" / "rhythm"
    else:
        monkeypatch.setattr(config, "_is_macos", lambda: False)
        xdg = tmp_path / "xdg"
        monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg))
        path = config.get_config_dir("rhythm")
        assert path == xdg / "rhythm"
