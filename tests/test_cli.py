"""Tests for CLI parsing and dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import builtins

from rhythm_slicer import cli
from rhythm_slicer.playlist import Playlist, Track


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


def test_parse_play_command() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["play", "song.mp3"])
    assert args.command == "play"
    assert args.path == "song.mp3"
    assert args.tui is False
    assert args.viz is None


def test_parse_tui_command() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["tui", "song.mp3"])
    assert args.command == "tui"
    assert args.path == "song.mp3"
    assert args.viz is None


def test_parse_tui_with_viz() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["tui", "song.mp3", "--viz", "matrix"])
    assert args.command == "tui"
    assert args.viz == "matrix"


def test_execute_play_command() -> None:
    player = DummyPlayer()
    args = cli.build_parser().parse_args(["play", "song.mp3"])
    result = cli._execute_command(player, args)
    assert result.exit_code == 0
    assert player.loaded_path == "song.mp3"
    assert player.played == 1


def test_wait_loop_exits_on_end() -> None:
    class SequencedPlayer(DummyPlayer):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0
            self.length_ms = 2000
            self.position_ms = 1000

        def get_state(self) -> str:
            self.calls += 1
            return "ended" if self.calls > 12 else "playing"

    player = SequencedPlayer()
    printed: list[str] = []
    current_time = 0.0

    def fake_print(message: str) -> None:
        printed.append(message)

    def fake_sleep(seconds: float) -> None:
        nonlocal current_time
        current_time += seconds

    def fake_now() -> float:
        return current_time

    cli._wait_for_playback(player, printer=fake_print, sleep=fake_sleep, now=fake_now)
    assert player.calls > 1
    assert printed


def test_wait_loop_ctrl_c_stops() -> None:
    player = DummyPlayer()

    def fake_sleep(_: float) -> None:
        raise KeyboardInterrupt

    cli._wait_for_playback(player, printer=lambda _: None, sleep=fake_sleep)
    assert player.stopped == 1


def test_run_tui_handles_import_error(monkeypatch, capsys) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "rhythm_slicer.tui":
            raise RuntimeError("boom")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    result = cli._run_tui("song.mp3", DummyPlayer(), None)
    assert result == 1
    assert "boom" in capsys.readouterr().err


def test_main_runs_play_and_wait(monkeypatch, capsys) -> None:
    player = DummyPlayer()
    monkeypatch.setattr(cli, "VlcPlayer", lambda: player)
    waited: list[bool] = []

    def fake_wait(*_args, **_kwargs) -> None:
        waited.append(True)

    monkeypatch.setattr(cli, "_wait_for_playback", fake_wait)
    monkeypatch.setattr(cli, "init_logging", lambda: Path("app.log"))
    monkeypatch.setattr(cli, "enable_faulthandler", lambda _: Path("hangdump.log"))
    exit_code = cli.main(["play", "song.mp3", "--wait"])
    assert exit_code == 0
    assert player.loaded_path == "song.mp3"
    assert waited == [True]
    assert "Playing: song.mp3" in capsys.readouterr().out


def test_main_runs_tui_path(monkeypatch) -> None:
    player = DummyPlayer()
    monkeypatch.setattr(cli, "VlcPlayer", lambda: player)
    monkeypatch.setattr(cli, "init_logging", lambda: Path("app.log"))
    monkeypatch.setattr(cli, "enable_faulthandler", lambda _: Path("hangdump.log"))
    monkeypatch.setattr(cli, "_run_tui", lambda *_args, **_kwargs: 0)
    exit_code = cli.main(["tui", "song.mp3"])
    assert exit_code == 0


def test_main_handles_vlc_error(monkeypatch, capsys) -> None:
    def boom():
        raise RuntimeError("missing")

    monkeypatch.setattr(cli, "VlcPlayer", boom)
    monkeypatch.setattr(cli, "init_logging", lambda: Path("app.log"))
    monkeypatch.setattr(cli, "enable_faulthandler", lambda _: Path("hangdump.log"))
    exit_code = cli.main(["play", "song.mp3"])
    assert exit_code == 1
    assert "missing" in capsys.readouterr().err


def test_execute_playlist_save(monkeypatch, tmp_path: Path) -> None:
    playlist = Playlist([Track(path=Path("one.mp3"), title="one.mp3")])
    saved: list[tuple[Path, str]] = []

    def fake_load(path: Path) -> Playlist:
        assert path == tmp_path / "input.m3u8"
        return playlist

    def fake_save(pl: Playlist, dest: Path, *, mode: str) -> None:
        assert pl is playlist
        saved.append((dest, mode))

    monkeypatch.setattr(cli, "load_from_input", fake_load)
    monkeypatch.setattr(cli, "save_m3u8", fake_save)
    args = cli.build_parser().parse_args(
        ["playlist", "save", str(tmp_path / "out.m3u8"), "--from", str(tmp_path / "input.m3u8")]
    )
    result = cli._execute_command(DummyPlayer(), args)
    assert result.exit_code == 0
    assert saved == [(tmp_path / "out.m3u8", "auto")]


def test_execute_playlist_save_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli, "load_from_input", lambda _: Playlist([]))
    args = cli.build_parser().parse_args(
        ["playlist", "save", str(tmp_path / "out.m3u8"), "--from", str(tmp_path / "input.m3u8")]
    )
    result = cli._execute_command(DummyPlayer(), args)
    assert result.exit_code == 1
    assert "No tracks" in (result.message or "")


def test_execute_playlist_show(monkeypatch, tmp_path: Path) -> None:
    playlist = Playlist(
        [
            Track(path=Path("one.mp3"), title="one.mp3"),
            Track(path=Path("two.mp3"), title="two.mp3"),
        ]
    )
    monkeypatch.setattr(cli, "load_from_input", lambda _: playlist)
    args = cli.build_parser().parse_args(
        ["playlist", "show", "--from", str(tmp_path / "input.m3u8")]
    )
    result = cli._execute_command(DummyPlayer(), args)
    assert result.exit_code == 0
    assert "1\tone.mp3" in (result.message or "")
    assert "2\ttwo.mp3" in (result.message or "")


def test_execute_playlist_unknown_command(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_from_input", lambda _: Playlist([]))
    args = cli.argparse.Namespace(
        command="playlist",
        playlist_cmd="nope",
        from_input="input.m3u8",
        dest="out.m3u8",
        absolute=False,
    )
    result = cli._execute_command(DummyPlayer(), args)
    assert result.exit_code == 2
