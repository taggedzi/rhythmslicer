"""Tests for SQLite-backed playlist store metadata caching."""

from __future__ import annotations

from pathlib import Path
import threading
import time

from rhythm_slicer.metadata import TrackMeta
from rhythm_slicer.playlist_store_sqlite import PlaylistStoreSQLite
from rhythm_slicer.ui.metadata_loader import MetadataLoader, TrackRef


def _wait_for(predicate, *, timeout: float = 1.0) -> None:
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if predicate():
            return
        time.sleep(0.01)


def _init_store(tmp_path: Path) -> tuple[PlaylistStoreSQLite, Path, int]:
    db_path = tmp_path / "playlist.db"
    audio = tmp_path / "song.mp3"
    audio.write_text("x", encoding="utf-8")
    store = PlaylistStoreSQLite(db_path=db_path)
    store.replace_paths("main", [audio])
    track_id = store.get_track_id_for_path(audio)
    assert track_id is not None
    return store, audio, track_id


def test_metadata_persists_across_store_reopen(tmp_path: Path) -> None:
    store, audio, track_id = _init_store(tmp_path)
    calls: list[Path] = []

    def notify(track_id: int, _path: Path, meta: TrackMeta | None, _gen: int) -> None:
        if meta is None:
            meta = TrackMeta(artist=None, title=None, album=None, duration_seconds=None)
        store.upsert_metadata(track_id, meta)

    loader = MetadataLoader(
        load_meta=lambda path: calls.append(path) or TrackMeta("Artist", "Title"),
        get_cached=store.fetch_metadata_if_valid,
        max_workers=1,
        queue_limit=5,
    )
    loader.start(notify)
    loader.set_generation(1)
    loader.update_visible([TrackRef(track_id, audio)])
    _wait_for(lambda: len(calls) == 1)
    loader.stop()
    store.close()

    store = PlaylistStoreSQLite(db_path=tmp_path / "playlist.db")
    track_id = store.get_track_id_for_path(audio)
    assert track_id is not None
    called = threading.Event()

    def notify_reopen(
        track_id: int, _path: Path, meta: TrackMeta | None, _gen: int
    ) -> None:
        if meta is None:
            meta = TrackMeta(artist=None, title=None, album=None, duration_seconds=None)
        store.upsert_metadata(track_id, meta)

    loader = MetadataLoader(
        load_meta=lambda path: called.set() or TrackMeta("Artist", "Title"),
        get_cached=store.fetch_metadata_if_valid,
        max_workers=1,
        queue_limit=5,
    )
    loader.start(notify_reopen)
    loader.set_generation(2)
    loader.update_visible([TrackRef(track_id, audio)])
    time.sleep(0.2)
    loader.stop()
    store.close()
    assert not called.is_set()


def test_metadata_invalidation_on_file_change(tmp_path: Path) -> None:
    store, audio, track_id = _init_store(tmp_path)
    calls: list[Path] = []

    def notify(track_id: int, _path: Path, meta: TrackMeta | None, _gen: int) -> None:
        if meta is None:
            meta = TrackMeta(artist=None, title=None, album=None, duration_seconds=None)
        store.upsert_metadata(track_id, meta)

    loader = MetadataLoader(
        load_meta=lambda path: calls.append(path) or TrackMeta("Artist", "Title"),
        get_cached=store.fetch_metadata_if_valid,
        max_workers=1,
        queue_limit=5,
    )
    loader.start(notify)
    loader.set_generation(1)
    loader.update_visible([TrackRef(track_id, audio)])
    _wait_for(lambda: len(calls) == 1)

    audio.write_text("changed", encoding="utf-8")
    loader.update_visible([TrackRef(track_id, audio)])
    _wait_for(lambda: len(calls) == 2)
    loader.stop()
    store.close()
