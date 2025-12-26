"""Tests for VLC player wrapper using fakes."""

from __future__ import annotations


import pytest

from rhythm_slicer import player_vlc


class FakeState:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeMediaPlayer:
    def __init__(self) -> None:
        self.media = None
        self.volume = None
        self.time = 0
        self.rate = 1.0

    def set_media(self, media: str) -> None:
        self.media = media

    def play(self) -> None:
        pass

    def pause(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def audio_set_volume(self, volume: int) -> None:
        self.volume = volume

    def get_state(self) -> FakeState:
        return FakeState("Playing")

    def get_time(self) -> int:
        return 1234 if self.time == 0 else self.time

    def get_length(self) -> int:
        return 5678

    def set_time(self, value: int) -> None:
        self.time = value

    def set_position(self, value: float) -> None:
        self.position = value

    def set_rate(self, rate: float) -> int:
        self.rate = rate
        return 0

    def get_rate(self) -> float:
        return self.rate


class FakeInstance:
    def __init__(self) -> None:
        self.player = FakeMediaPlayer()

    def media_player_new(self) -> FakeMediaPlayer:
        return self.player

    def media_new(self, path: str) -> str:
        return path


class FakeVlc:
    @staticmethod
    def Instance() -> FakeInstance:
        return FakeInstance()


def test_player_state_and_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_vlc, "vlc", FakeVlc)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player = player_vlc.VlcPlayer()
    player.load("track.mp3")
    assert player.current_media == "track.mp3"
    assert player.get_state() == "playing"
    assert player.get_position_ms() == 1234
    assert player.get_length_ms() == 5678
    assert player.seek_ms(5000) is True
    assert player.set_position_ratio(0.5) is True


def test_missing_vlc_raises_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_vlc, "vlc", None)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", RuntimeError("missing"))
    with pytest.raises(RuntimeError):
        player_vlc.VlcPlayer()


def test_load_vlc_import_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "vlc":
            raise ModuleNotFoundError("vlc")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(player_vlc, "vlc", None)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player_vlc._load_vlc()
    assert player_vlc.vlc is None
    assert isinstance(player_vlc._VLC_IMPORT_ERROR, ModuleNotFoundError)


def test_load_vlc_success(monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    class DummyVlc:
        pass

    monkeypatch.setitem(sys.modules, "vlc", DummyVlc)
    monkeypatch.setattr(player_vlc, "vlc", None)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player_vlc._load_vlc()
    assert player_vlc.vlc is DummyVlc
    assert player_vlc._VLC_IMPORT_ERROR is None


def test_player_state_unknown_on_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorPlayer(FakeMediaPlayer):
        def get_state(self):  # type: ignore[override]
            raise RuntimeError("bad")

        def event_manager(self):  # type: ignore[override]
            raise RuntimeError("no events")

    class ErrorInstance(FakeInstance):
        def media_player_new(self) -> ErrorPlayer:  # type: ignore[override]
            return ErrorPlayer()

    class ErrorVlc:
        @staticmethod
        def Instance() -> ErrorInstance:
            return ErrorInstance()

    monkeypatch.setattr(player_vlc, "vlc", ErrorVlc)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player = player_vlc.VlcPlayer()
    assert player.get_state() == "unknown"


def test_player_position_and_seek_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorPlayer(FakeMediaPlayer):
        def get_time(self):  # type: ignore[override]
            return -1

        def get_length(self):  # type: ignore[override]
            return -1

        def set_time(self, value: int) -> None:  # type: ignore[override]
            raise RuntimeError("bad")

        def set_position(self, value: float) -> None:  # type: ignore[override]
            raise RuntimeError("bad")

    class ErrorInstance(FakeInstance):
        def media_player_new(self) -> ErrorPlayer:  # type: ignore[override]
            return ErrorPlayer()

    class ErrorVlc:
        @staticmethod
        def Instance() -> ErrorInstance:
            return ErrorInstance()

    monkeypatch.setattr(player_vlc, "vlc", ErrorVlc)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player = player_vlc.VlcPlayer()
    assert player.get_position_ms() is None
    assert player.get_length_ms() is None
    assert player.seek_ms(1000) is False
    assert player.set_position_ratio(0.25) is False


def test_player_controls_and_end_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_vlc, "vlc", FakeVlc)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player = player_vlc.VlcPlayer()
    player.load("track.mp3")
    player.play()
    player.pause()
    player.stop()
    player.set_volume(10)
    assert player.current_media == "track.mp3"
    assert player.consume_end_reached() is False
    player.signal_end_reached()
    assert player.consume_end_reached() is True
    assert player.consume_end_reached() is False


def test_player_playback_rate_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(player_vlc, "vlc", FakeVlc)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player = player_vlc.VlcPlayer()
    assert player.set_playback_rate(1.5) is True
    assert player.get_playback_rate() == 1.5


def test_player_playback_rate_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    class ErrorPlayer(FakeMediaPlayer):
        def set_rate(self, rate: float) -> int:  # type: ignore[override]
            raise RuntimeError("bad")

        def get_rate(self):  # type: ignore[override]
            return -1

    class ErrorInstance(FakeInstance):
        def media_player_new(self) -> ErrorPlayer:  # type: ignore[override]
            return ErrorPlayer()

    class ErrorVlc:
        @staticmethod
        def Instance() -> ErrorInstance:
            return ErrorInstance()

    monkeypatch.setattr(player_vlc, "vlc", ErrorVlc)
    monkeypatch.setattr(player_vlc, "_VLC_IMPORT_ERROR", None)
    player = player_vlc.VlcPlayer()
    assert player.set_playback_rate(1.25) is False
    assert player.get_playback_rate() is None


def test_attach_end_reached_event_skips_when_missing_vlc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    player = player_vlc.VlcPlayer.__new__(player_vlc.VlcPlayer)
    monkeypatch.setattr(player_vlc, "vlc", None)
    player._player = FakeMediaPlayer()  # type: ignore[attr-defined]
    player._attach_end_reached_event()
