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


def _seed_playlist(
    tmp_path: Path, *, count: int = 5
) -> tuple[PlaylistStoreSQLite, list[int]]:
    store = PlaylistStoreSQLite(db_path=tmp_path / "playlist.db")
    paths = []
    for idx in range(count):
        path = tmp_path / f"track_{idx}.mp3"
        path.write_text("x", encoding="utf-8")
        paths.append(path)
    store.replace_paths("main", paths)
    track_ids = store.list_track_ids("main")
    return store, track_ids


def test_remove_tracks_bulk_rebuilds_positions(tmp_path: Path) -> None:
    store, track_ids = _seed_playlist(tmp_path, count=5)
    removed = store.remove_tracks_bulk("main", [track_ids[0], track_ids[2], track_ids[4]])
    assert removed == 3
    remaining = store.list_track_ids("main")
    assert remaining == [track_ids[1], track_ids[3]]
    with store._lock:
        rows = store._conn.execute(
            """
            SELECT position, track_id
            FROM playlist_items
            WHERE playlist_id = ?
            ORDER BY position
            """,
            ("main",),
        ).fetchall()
    assert [int(row["position"]) for row in rows] == [0, 1]
    assert [int(row["track_id"]) for row in rows] == remaining


def test_remove_tracks_bulk_cancel_rolls_back(tmp_path: Path) -> None:
    store, track_ids = _seed_playlist(tmp_path, count=8)
    cancel_event = threading.Event()

    def progress(done: int, total: int) -> None:
        if done >= total // 2:
            cancel_event.set()

    removed = store.remove_tracks_bulk(
        "main", track_ids, cancel=cancel_event, progress=progress
    )
    assert removed == 0
    assert store.list_track_ids("main") == track_ids


def test_remove_tracks_bulk_commits_once(tmp_path: Path) -> None:
    store, track_ids = _seed_playlist(tmp_path, count=3)
    commits: list[str] = []

    def trace(sql: str) -> None:
        if sql.strip().upper() == "COMMIT":
            commits.append(sql)

    store._conn.set_trace_callback(trace)
    store.remove_tracks_bulk("main", [track_ids[0]])
    store._conn.set_trace_callback(None)
    assert len(commits) == 1
