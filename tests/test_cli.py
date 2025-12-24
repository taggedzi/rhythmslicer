"""Tests for CLI parsing and dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import builtins

from rhythm_slicer import cli


@dataclass
class DummyPlayer:
    loaded_path: str | None = None
    played: int = 0
    paused: int = 0
    stopped: int = 0
    volume: int | None = None
    position_ms: int | None = None
    length_ms: int | None = None

    def load(self, path: str) -> None:
        self.loaded_path = path

    def play(self) -> None:
        self.played += 1

    def pause(self) -> None:
        self.paused += 1

    def stop(self) -> None:
        self.stopped += 1

    def set_volume(self, volume: int) -> None:
        self.volume = volume

    def get_state(self) -> str:
        return "playing"

    def get_position_ms(self) -> int | None:
        return self.position_ms

    def get_length_ms(self) -> int | None:
        return self.length_ms

    @property
    def current_media(self) -> str | None:
        return self.loaded_path


def test_parse_path_argument() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["song.mp3"])
    assert args.path == "song.mp3"
    assert args.viz is None


def test_parse_with_viz() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["song.mp3", "--viz", "matrix"])
    assert args.viz == "matrix"


def test_run_tui_handles_import_error(monkeypatch, capsys) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rhythm_slicer.tui":
            raise ImportError("boom")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = cli._run_tui("song.mp3", DummyPlayer(), None)
    assert result == 1
    assert "boom" in capsys.readouterr().err


def test_main_runs_tui_path(monkeypatch) -> None:
    player = DummyPlayer()
    monkeypatch.setattr(cli, "VlcPlayer", lambda: player)
    monkeypatch.setattr(cli, "init_logging", lambda: Path("app.log"))
    monkeypatch.setattr(cli, "enable_faulthandler", lambda _: Path("hangdump.log"))
    monkeypatch.setattr(cli, "_run_tui", lambda *_args, **_kwargs: 0)
    exit_code = cli.main(["song.mp3"])
    assert exit_code == 0


def test_main_runs_tui_by_default(monkeypatch) -> None:
    player = DummyPlayer()
    monkeypatch.setattr(cli, "VlcPlayer", lambda: player)
    monkeypatch.setattr(cli, "init_logging", lambda: Path("app.log"))
    monkeypatch.setattr(cli, "enable_faulthandler", lambda _: Path("hangdump.log"))
    monkeypatch.setattr(cli, "_run_tui", lambda *_args, **_kwargs: 0)
    exit_code = cli.main([])
    assert exit_code == 0


def test_main_handles_vlc_error(monkeypatch, capsys) -> None:
    def boom():
        raise RuntimeError("missing")

    monkeypatch.setattr(cli, "VlcPlayer", boom)
    monkeypatch.setattr(cli, "init_logging", lambda: Path("app.log"))
    monkeypatch.setattr(cli, "enable_faulthandler", lambda _: Path("hangdump.log"))
    exit_code = cli.main(["song.mp3"])
    assert exit_code == 1
    assert "missing" in capsys.readouterr().err


def test_thread_exceptions_dump_threads(monkeypatch) -> None:
    from types import SimpleNamespace
    import threading

    original_excepthook = threading.excepthook
    calls: list[str] = []

    def record_dump_threads(message: str) -> None:
        calls.append(message)

    monkeypatch.setattr(cli, "VlcPlayer", lambda: DummyPlayer())
    monkeypatch.setattr(cli, "init_logging", lambda: Path("app.log"))
    monkeypatch.setattr(cli, "enable_faulthandler", lambda _: Path("hangdump.log"))
    monkeypatch.setattr(cli, "_run_tui", lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(cli, "dump_threads", record_dump_threads)

    try:
        cli.main([])
        fake_thread = SimpleNamespace(name="worker")
        fake_args = SimpleNamespace(
            exc_type=RuntimeError,
            exc_value=RuntimeError("boom"),
            exc_traceback=None,
            thread=fake_thread,
        )
        threading.excepthook(fake_args)
    finally:
        threading.excepthook = original_excepthook

    assert calls == ["thread exception in worker"]
