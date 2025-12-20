"""Tests for TUI helpers and keybindings."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from rhythm_slicer import tui
from rhythm_slicer.config import AppConfig
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
        self._end_reached = False

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

    def consume_end_reached(self) -> bool:
        if self._end_reached:
            self._end_reached = False
            return True
        return False

    def signal_end_reached(self) -> None:
        self._end_reached = True


class DummyPlayerNoSeek(DummyPlayer):
    seek_ms = None  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def stub_config(monkeypatch) -> None:
    monkeypatch.setattr(tui, "load_config", lambda: AppConfig())
    monkeypatch.setattr(tui, "save_config", lambda cfg: None)


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


def test_toggle_playback_plays_when_stopped() -> None:
    player = DummyPlayer(state="stopped")
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


def test_next_index_respects_wrap_and_shuffle() -> None:
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    app.playlist = Playlist(
        [
            Track(path=Path("one.mp3"), title="one.mp3"),
            Track(path=Path("two.mp3"), title="two.mp3"),
            Track(path=Path("three.mp3"), title="three.mp3"),
        ]
    )
    app._play_order = [1, 0, 2]
    app._play_order_pos = 2
    assert app._next_index(wrap=False) is None
    assert app._next_index(wrap=True) == 1


def test_end_reached_advances_track() -> None:
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    app.playlist = Playlist(
        [
            Track(path=Path("one.mp3"), title="one.mp3"),
            Track(path=Path("two.mp3"), title="two.mp3"),
        ]
    )
    app.playlist.set_index(0)
    app._reset_play_order()
    app.player.signal_end_reached()
    app._on_tick()
    assert app.playlist.index == 1


def test_end_reached_repeats_one() -> None:
    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    app.playlist = Playlist(
        [
            Track(path=Path("one.mp3"), title="one.mp3"),
            Track(path=Path("two.mp3"), title="two.mp3"),
        ]
    )
    app.playlist.set_index(1)
    app._repeat_mode = "one"
    app._reset_play_order()
    app.player.signal_end_reached()
    app._on_tick()
    assert app.playlist.index == 1
    assert player.play_calls == 1


def test_end_reached_wraps_when_repeat_all() -> None:
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    app.playlist = Playlist(
        [
            Track(path=Path("one.mp3"), title="one.mp3"),
            Track(path=Path("two.mp3"), title="two.mp3"),
        ]
    )
    app.playlist.set_index(1)
    app._repeat_mode = "all"
    app._reset_play_order()
    app.player.signal_end_reached()
    app._on_tick()
    assert app.playlist.index == 0


def test_playlist_footer_empty() -> None:
    playlist = Playlist([])
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3", playlist=playlist)
    assert "Track: --/0" in app._render_playlist_footer()


def test_playlist_footer_single_track() -> None:
    tracks = [Track(path=Path("one.mp3"), title="one.mp3")]
    playlist = Playlist(tracks)
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3", playlist=playlist)
    assert "Track: 1/1" in app._render_playlist_footer()


def test_playlist_footer_multiple_tracks() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
        Track(path=Path("three.mp3"), title="three.mp3"),
    ]
    playlist = Playlist(tracks)
    playlist.set_index(1)
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3", playlist=playlist)
    assert "Track: 2/3" in app._render_playlist_footer()


def test_playlist_footer_after_removal() -> None:
    tracks = [
        Track(path=Path("one.mp3"), title="one.mp3"),
        Track(path=Path("two.mp3"), title="two.mp3"),
        Track(path=Path("three.mp3"), title="three.mp3"),
    ]
    playlist = Playlist(tracks)
    playlist.set_index(1)
    playlist.remove(1)
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3", playlist=playlist)
    assert "Track: 2/2" in app._render_playlist_footer()


def test_render_modes_repeat_and_shuffle() -> None:
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    app._repeat_mode = "off"
    app._shuffle = False
    assert app._render_modes() == "R:OFF S:OFF"
    app._repeat_mode = "one"
    app._shuffle = True
    assert app._render_modes() == "R:ONE S:ON"
    app._repeat_mode = "all"
    app._shuffle = False
    assert app._render_modes() == "R:ALL S:OFF"


def test_render_repeat_and_shuffle_labels() -> None:
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    app._repeat_mode = "all"
    app._shuffle = True
    repeat = app._render_repeat_label()
    shuffle = app._render_shuffle_label()
    assert repeat.plain == "R:ALL"
    assert repeat.style == "#9cff57"
    assert shuffle.plain == "S:ON"
    assert shuffle.style == "#9cff57"


def test_render_transport_label_play_pause() -> None:
    player = DummyPlayer(state="playing")
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    assert app._render_transport_label().plain == "[ PAUSE ]"
    player.state = "paused"
    assert app._render_transport_label().plain == "[ PLAY ] "


def test_transport_play_pause_clicks() -> None:
    player = DummyPlayer(state="paused")
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    app._handle_transport_action("key_playpause")
    assert player.play_calls == 1

def test_open_path_calls_set_playlist(tmp_path: Path, monkeypatch) -> None:
    playlist = Playlist([Track(path=Path("one.mp3"), title="one.mp3")])
    target = tmp_path / "music"
    target.mkdir()

    def fake_load(path: Path) -> Playlist:
        assert path == target
        return playlist

    calls: list[tuple[Playlist, Path]] = []

    async def fake_set(new_playlist: Playlist, source_path: Path) -> None:
        calls.append((new_playlist, source_path))

    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    monkeypatch.setattr(tui, "load_from_input", fake_load)
    app.set_playlist_from_open = fake_set  # type: ignore[assignment]

    asyncio.run(app._handle_open_path(str(target)))
    assert calls == [(playlist, target)]


def test_open_path_missing_shows_message(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    asyncio.run(app._handle_open_path(str(missing)))
    assert app._message is not None
    assert app._message.text == "Path not found"


def test_open_path_empty_playlist_shows_message(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / "empty.m3u"
    target.write_text("", encoding="utf-8")

    def fake_load(path: Path) -> Playlist:
        assert path == target
        return Playlist([])

    player = DummyPlayer()
    app = tui.RhythmSlicerApp(player=player, path="song.mp3")
    monkeypatch.setattr(tui, "load_from_input", fake_load)

    asyncio.run(app._handle_open_path(str(target)))
    assert app._message is not None
    assert app._message.text == "No supported audio files found"
    assert player.play_calls == 0


def test_open_path_recursive_loads_sorted_tracks(tmp_path: Path) -> None:
    root = tmp_path / "music"
    sub = root / "sub"
    sub.mkdir(parents=True)
    (root / "b.mp3").write_text("b", encoding="utf-8")
    (sub / "a.mp3").write_text("a", encoding="utf-8")

    calls: list[Playlist] = []

    async def fake_set(new_playlist: Playlist, source_path: Path) -> None:
        calls.append(new_playlist)

    app = tui.RhythmSlicerApp(player=DummyPlayer(), path="song.mp3")
    app.set_playlist_from_open = fake_set  # type: ignore[assignment]

    asyncio.run(app._handle_open_path(str(root), recursive=True))
    assert len(calls) == 1
    titles = [track.title for track in calls[0].tracks]
    assert titles == ["b.mp3", "a.mp3"]
    assert app._message is not None
    assert app._message.text == "Loaded 2 tracks (recursive)"


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
