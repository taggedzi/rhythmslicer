"""Tests for CLI parsing and dispatch."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

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


def test_volume_validation() -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["volume", "101"])


def test_execute_play_command() -> None:
    player = DummyPlayer()
    args = cli.build_parser().parse_args(["play", "song.mp3"])
    result = cli._execute_command(player, args)
    assert result.exit_code == 0
    assert player.loaded_path == "song.mp3"
    assert player.played == 1


def test_execute_status_command() -> None:
    player = DummyPlayer()
    args = cli.build_parser().parse_args(["status"])
    result = cli._execute_command(player, args)
    assert result.exit_code == 0
    assert "State: playing" in (result.message or "")


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

    cli._wait_for_playback(
        player, printer=fake_print, sleep=fake_sleep, now=fake_now
    )
    assert player.calls > 1
    assert printed


def test_wait_loop_ctrl_c_stops() -> None:
    player = DummyPlayer()

    def fake_sleep(_: float) -> None:
        raise KeyboardInterrupt

    cli._wait_for_playback(player, printer=lambda _: None, sleep=fake_sleep)
    assert player.stopped == 1
