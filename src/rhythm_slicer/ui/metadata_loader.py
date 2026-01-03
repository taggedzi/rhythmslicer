from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
import queue
import threading

from rhythm_slicer.metadata import TrackMeta, get_cached_track_meta, get_track_meta


@dataclass(frozen=True)
class TrackRef:
    track_id: int
    path: Path


class MetadataLoader:
    """Background metadata loader with bounded concurrency and generation guards."""

    def __init__(
        self,
        *,
        load_meta: Callable[[Path], TrackMeta] = get_track_meta,
        get_cached: Callable[[int, Path], TrackMeta | None] | None = None,
        max_workers: int = 4,
        queue_limit: int = 200,
    ) -> None:
        self._load_meta = load_meta
        self._get_cached = get_cached or (
            lambda _track_id, path: get_cached_track_meta(path)
        )
        self._max_workers = max(1, max_workers)
        self._queue_limit = max(1, queue_limit)
        self._queue: queue.Queue[tuple[int, int, Path]] = queue.Queue()
        self._pending: set[int] = set()
        self._desired: dict[int, Path] = {}
        self._generation = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._notify: Callable[[int, Path, TrackMeta | None, int], None] | None = None

    def start(self, notify: Callable[[int, Path, TrackMeta | None, int], None]) -> None:
        if self._threads:
            return
        self._notify = notify
        self._stop.clear()
        for idx in range(self._max_workers):
            thread = threading.Thread(
                target=self._worker,
                name=f"MetaLoader-{idx}",
                daemon=True,
            )
            thread.start()
            self._threads.append(thread)

    def stop(self) -> None:
        if not self._threads:
            return
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=0.5)
        self._threads.clear()
        self._notify = None
        with self._lock:
            self._pending.clear()
            self._desired.clear()
        self._drain_queue()

    def set_generation(self, generation: int) -> None:
        with self._lock:
            self._generation = generation
            self._pending.clear()
            self._desired.clear()
        self._drain_queue()

    def update_visible(self, tracks: Iterable[TrackRef]) -> None:
        desired = {track.track_id: track.path for track in tracks}
        with self._lock:
            self._desired = desired
            generation = self._generation
            pending = set(self._pending)
        to_enqueue = [track_id for track_id in desired if track_id not in pending]
        for track_id in to_enqueue:
            if self._queue.qsize() >= self._queue_limit:
                break
            with self._lock:
                if track_id in self._pending:
                    continue
                self._pending.add(track_id)
            self._queue.put((generation, track_id, desired[track_id]))

    def _drain_queue(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                generation, track_id, path = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if self._stop.is_set():
                break
            if not self._should_process(generation, track_id):
                self._discard_pending(track_id)
                continue
            meta = self._get_cached(track_id, path)
            if meta is None:
                try:
                    meta = self._load_meta(path)
                except Exception:
                    meta = None
            if not self._should_process(generation, track_id):
                self._discard_pending(track_id)
                continue
            notify = self._notify
            if notify is not None:
                try:
                    notify(track_id, path, meta, generation)
                except Exception:
                    pass
            self._discard_pending(track_id)

    def _should_process(self, generation: int, track_id: int) -> bool:
        with self._lock:
            return generation == self._generation and track_id in self._desired

    def _discard_pending(self, track_id: int) -> None:
        with self._lock:
            self._pending.discard(track_id)
