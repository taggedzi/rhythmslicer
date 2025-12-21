"""Tests for config persistence."""

from __future__ import annotations

import json
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
