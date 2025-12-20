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

    @property
    def current_media(self) -> str | None:
        return self.loaded_path


def test_parse_play_command() -> None:
    parser = cli.build_parser()
    args = parser.parse_args(["play", "song.mp3"])
    assert args.command == "play"
    assert args.path == "song.mp3"


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
