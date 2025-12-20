"""Tests for TUI helpers and keybindings."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer import tui
from rhythm_slicer.playlist import Playlist, Track


class DummyPlayer:
    def __init__(self, state: str = "playing") -> None:
        self.state = state
        self.play_calls = 0
        self.pause_calls = 0
        self.stop_calls = 0
        self.volume = 100
        self.seeks: list[int] = []
        self.loaded: list[str] = []

    def get_state(self) -> str:
        return self.state

    def load(self, path: str) -> None:
        self.loaded.append(path)

    def play(self) -> None:
        self.play_calls += 1
        self.state = "playing"

    def pause(self) -> None:
        self.pause_calls += 1
        self.state = "paused"

    def stop(self) -> None:
        self.stop_calls += 1
        self.state = "stopped"

    def set_volume(self, volume: int) -> None:
        self.volume = volume

    def get_position_ms(self) -> int:
        return 1000

    def get_length_ms(self) -> int:
        return 5000

    def seek_ms(self, delta_ms: int) -> bool:
        self.seeks.append(delta_ms)
        return True


class DummyPlayerNoSeek(DummyPlayer):
    seek_ms = None  # type: ignore[assignment]


def test_visualizer_bars_deterministic() -> None:
    bars = tui.visualizer_bars(seed_ms=1000, width=4, height=3)
    assert bars == [2, 2, 0, 0]


def test_render_visualizer() -> None:
    frame = tui.render_visualizer([2, 2, 0, 0], height=3)
    assert frame == "    \n##  \n##  "


def test_toggle_playback_pauses_when_playing() -> None:
    player = DummyPlayer(state="playing")
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    app.action_toggle_playback()
    assert player.pause_calls == 1


def test_toggle_playback_plays_when_paused() -> None:
    player = DummyPlayer(state="paused")
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    app.action_toggle_playback()
    assert player.play_calls == 1


def test_seek_forward_calls_player() -> None:
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    app.action_seek_forward()
    assert player.seeks == [5000]


def test_seek_shows_message_when_unsupported() -> None:
    player = DummyPlayerNoSeek()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    app.action_seek_forward()
    assert app._message is not None
    assert app._message.text == "Seek unsupported"


def test_volume_adjustments() -> None:
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    app.action_volume_down()
    assert player.volume == 95
    app.action_volume_up()
    assert player.volume == 100


def test_ratio_from_click() -> None:
    assert tui.ratio_from_click(0, 10) == 0.0
    assert tui.ratio_from_click(9, 10) == 1.0
    assert tui.ratio_from_click(5, 11) == 0.5


def test_target_ms_from_ratio() -> None:
    assert tui.target_ms_from_ratio(1000, 0.0) == 0
    assert tui.target_ms_from_ratio(1000, 0.5) == 500
    assert tui.target_ms_from_ratio(1000, 1.0) == 1000


def test_build_play_order_no_shuffle() -> None:
    rng = __import__("random").Random(1)
    order, pos = tui.build_play_order(4, 2, False, rng)
    assert order == [0, 1, 2, 3]
    assert pos == 2


def test_build_play_order_shuffle_keeps_current() -> None:
    rng = __import__("random").Random(2)
    order, pos = tui.build_play_order(5, 3, True, rng)
    assert order[pos] == 3


def test_next_prev_respects_wrap() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
    ]
    playlist = Playlist(tracks)
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3", playlist=playlist)
    app._reset_play_order()
    assert app._next_index(wrap=False) == 1
    assert app._next_index(wrap=False) is None
    assert app._prev_index(wrap=False) == 0


def test_shuffle_toggle_keeps_current_index() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
        Track(path=Path("three.mp3"), title="three.mp3"),
    ]
    playlist = Playlist(tracks)
    playlist.set_index(1)
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(
        player=player,
        path="song.mp3",
        playlist=playlist,
        rng=__import__("random").Random(3),
    )
    app._reset_play_order()
    original = playlist.index
    app._shuffle = True
    app._reset_play_order()
    assert app._play_order[app._play_order_pos] == original


def test_next_track_advances_playlist() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
    ]
    playlist = Playlist(tracks)
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3", playlist=playlist)
    app._reset_play_order()
    app.action_next_track()
    assert playlist.index == 1
    assert player.loaded[-1] == "two.mp3"


def test_play_selected_uses_list_selection() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
    ]
    playlist = Playlist(tracks)
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3", playlist=playlist)

    app._selection_index = 1
    playlist.set_index(1)
    app.action_play_selected()
    assert playlist.index == 1
    assert player.loaded[-1] == "two.mp3"


def test_remove_current_track_plays_next() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
    ]
    playlist = Playlist(tracks)
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3", playlist=playlist)

    app._selection_index = 0
    playlist.set_index(0)
    app._play_current_track()
    app.action_remove_selected()
    assert playlist.index == 0
    assert playlist.current() == tracks[1]
    assert player.loaded[-1] == "two.mp3"


def test_remove_current_track_stops_when_empty() -> None:
    tracks = [Track(path=Path("one.mp3"), title="one.mp3")]
    playlist = Playlist(tracks)
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3", playlist=playlist)

    app._selection_index = 0
    playlist.set_index(0)
    app._play_current_track()
    app.action_remove_selected()
    assert playlist.is_empty()
    assert player.stop_calls == 1
    assert app._message is not None
    assert app._message.text == "Playlist empty"
