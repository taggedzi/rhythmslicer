from __future__ import annotations

import asyncio

import pytest

from rhythm_slicer.hackscript import HackFrame
from rhythm_slicer.ui.frame_player import FramePlayer


class _Timer:
    def __init__(self) -> None:
        self.stopped = False

    def stop(self) -> None:
        self.stopped = True


class _App:
    def __init__(self) -> None:
        self.frames: list[HackFrame] = []
        self.messages: list[tuple[str, str]] = []
        self.timers: list[tuple[float, object]] = []

    def _show_frame(self, frame: HackFrame) -> None:
        self.frames.append(frame)

    def _set_message(self, message: str, level: str = "info") -> None:
        self.messages.append((message, level))

    def set_timer(self, delay: float, callback) -> _Timer:
        self.timers.append((delay, callback))
        return _Timer()


def test_start_with_first_frame_schedules_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _App()
    player = FramePlayer(app)
    first = HackFrame(text="first", hold_ms=5)
    frames = iter([HackFrame(text="next", hold_ms=50)])
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: object())

    player.start(frames, first_frame=first)

    assert app.frames == [first]
    assert player.is_running is True
    assert app.timers
    assert app.timers[0][0] == pytest.approx(0.01)


def test_start_without_first_frame_advances() -> None:
    app = _App()
    player = FramePlayer(app)
    seen: list[str] = []

    def fake_advance() -> None:
        seen.append("advance")

    player._advance = fake_advance  # type: ignore[assignment]
    player.start(iter([]))

    assert seen == ["advance"]


def test_schedule_next_without_loop_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _App()
    player = FramePlayer(app)
    player._frames = iter([HackFrame(text="next", hold_ms=10)])
    monkeypatch.setattr(
        asyncio, "get_running_loop", lambda: (_ for _ in ()).throw(RuntimeError())
    )

    player._schedule_next(10)

    assert player.is_running is False
    assert player._timer is None


def test_stop_clears_timer_and_frames() -> None:
    app = _App()
    player = FramePlayer(app)
    player._frames = iter([HackFrame(text="frame", hold_ms=10)])
    player._timer = _Timer()

    player.stop()

    assert player._frames is None
    assert player._timer is None


def test_advance_without_frames_returns() -> None:
    app = _App()
    player = FramePlayer(app)

    player._advance()

    assert app.frames == []


def test_advance_handles_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _App()
    player = FramePlayer(app)

    class _Boom:
        def __next__(self) -> HackFrame:
            raise ValueError("boom")

        def __iter__(self):
            return self

    player._frames = _Boom()
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: object())

    player._advance()

    assert player.is_running is False
    assert app.messages[-1] == ("Visualizer error: boom", "error")


def test_advance_shows_frame_and_schedules(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _App()
    player = FramePlayer(app)
    frames = iter([HackFrame(text="frame", hold_ms=20)])
    player._frames = frames
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: object())

    player._advance()

    assert app.frames[-1].text == "frame"
    assert app.timers[-1][0] == pytest.approx(0.02)
