from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
import threading
import time
from typing import Iterable, Literal, Sequence

from rhythm_slicer.config import get_config_dir
from rhythm_slicer.metadata import METADATA_EXTRACTOR_VERSION, TrackMeta

SortMode = Literal["position", "title", "artist", "album", "duration", "path"]
SortDir = Literal["asc", "desc"]


@dataclass(frozen=True)
class TrackRow:
    track_id: int
    path: Path
    title: str | None
    artist: str | None
    album: str | None
    duration_seconds: float | None
    has_metadata: bool


@dataclass
class PlaylistView:
    playlist_id: str
    filter_text: str = ""
    sort_mode: SortMode = "position"
    sort_dir: SortDir = "asc"


def default_db_path(app_name: str = "rhythm-slicer") -> Path:
    try:
        base = get_config_dir(app_name)
    except OSError:
        base = Path.cwd() / ".rhythm-slicer"
        base.mkdir(parents=True, exist_ok=True)
    return base / "playlist.db"


class PlaylistStoreSQLite:
    def __init__(self, db_path: Path | None = None) -> None:
        self._path = db_path or default_db_path()
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._views: dict[str, PlaylistView] = {}
        self._apply_pragmas()
        self._ensure_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def view(self, playlist_id: str) -> PlaylistView:
        view = self._views.get(playlist_id)
        if view is None:
            view = PlaylistView(playlist_id=playlist_id)
            self._views[playlist_id] = view
        return view

    def set_filter(self, playlist_id: str, filter_text: str) -> None:
        view = self.view(playlist_id)
        view.filter_text = filter_text or ""

    def set_sort(
        self,
        playlist_id: str,
        sort_mode: SortMode,
        sort_dir: SortDir = "asc",
    ) -> None:
        view = self.view(playlist_id)
        view.sort_mode = sort_mode
        view.sort_dir = sort_dir

    def ensure_playlist(self, playlist_id: str, name: str | None = None) -> None:
        now = int(time.time())
        with self._lock:
            self._ensure_playlist_locked(playlist_id, name, now)
            self._conn.commit()

    def replace_paths(self, playlist_id: str, paths: Sequence[Path]) -> None:
        now = int(time.time())
        with self._lock:
            self._ensure_playlist_locked(playlist_id, None, now)
            self._conn.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            )
            position = 0
            for path in paths:
                track_id = self._upsert_track(path)
                if track_id is None:
                    continue
                self._conn.execute(
                    """
                    INSERT INTO playlist_items (playlist_id, position, track_id)
                    VALUES (?, ?, ?)
                    """,
                    (playlist_id, position, track_id),
                )
                position += 1
            self._conn.execute(
                "UPDATE playlists SET updated_at = ? WHERE playlist_id = ?",
                (now, playlist_id),
            )
            self._conn.commit()

    def add_paths(self, playlist_id: str, paths: Sequence[Path]) -> None:
        if not paths:
            return
        now = int(time.time())
        with self._lock:
            self._ensure_playlist_locked(playlist_id, None, now)
            existing = {
                row["track_id"]
                for row in self._conn.execute(
                    "SELECT track_id FROM playlist_items WHERE playlist_id = ?",
                    (playlist_id,),
                ).fetchall()
            }
            position_row = self._conn.execute(
                """
                SELECT COALESCE(MAX(position), -1) AS max_pos
                FROM playlist_items
                WHERE playlist_id = ?
                """,
                (playlist_id,),
            ).fetchone()
            position = int(position_row["max_pos"]) if position_row else -1
            for path in paths:
                track_id = self._upsert_track(path)
                if track_id is None or track_id in existing:
                    continue
                position += 1
                self._conn.execute(
                    """
                    INSERT INTO playlist_items (playlist_id, position, track_id)
                    VALUES (?, ?, ?)
                    """,
                    (playlist_id, position, track_id),
                )
                existing.add(track_id)
            self._conn.execute(
                "UPDATE playlists SET updated_at = ? WHERE playlist_id = ?",
                (now, playlist_id),
            )
            self._conn.commit()

    def remove_track(self, playlist_id: str, track_id: int) -> None:
        now = int(time.time())
        with self._lock:
            row = self._conn.execute(
                """
                SELECT position FROM playlist_items
                WHERE playlist_id = ? AND track_id = ?
                """,
                (playlist_id, track_id),
            ).fetchone()
            if not row:
                return
            position = int(row["position"])
            self._conn.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ? AND track_id = ?",
                (playlist_id, track_id),
            )
            self._conn.execute(
                """
                UPDATE playlist_items
                SET position = position - 1
                WHERE playlist_id = ? AND position > ?
                """,
                (playlist_id, position),
            )
            self._conn.execute(
                "UPDATE playlists SET updated_at = ? WHERE playlist_id = ?",
                (now, playlist_id),
            )
            self._conn.commit()

    def move_tracks(
        self,
        playlist_id: str,
        track_ids: Iterable[int],
        direction: Literal["up", "down"],
    ) -> None:
        selected = list(dict.fromkeys(track_ids))
        if not selected:
            return
        with self._lock:
            ordered = [
                row["track_id"]
                for row in self._conn.execute(
                    """
                    SELECT track_id FROM playlist_items
                    WHERE playlist_id = ?
                    ORDER BY position
                    """,
                    (playlist_id,),
                ).fetchall()
            ]
            index_map = {track_id: idx for idx, track_id in enumerate(ordered)}
            selected_indices = [
                index_map[track_id] for track_id in selected if track_id in index_map
            ]
            if not selected_indices:
                return
            reordered = list(ordered)
            selected_set = set(selected_indices)
            if direction == "up":
                for idx in sorted(selected_indices):
                    if idx == 0 or (idx - 1) in selected_set:
                        continue
                    reordered[idx - 1], reordered[idx] = (
                        reordered[idx],
                        reordered[idx - 1],
                    )
                    selected_set.remove(idx)
                    selected_set.add(idx - 1)
            else:
                for idx in sorted(selected_indices, reverse=True):
                    if idx >= len(reordered) - 1 or (idx + 1) in selected_set:
                        continue
                    reordered[idx + 1], reordered[idx] = (
                        reordered[idx],
                        reordered[idx + 1],
                    )
                    selected_set.remove(idx)
                    selected_set.add(idx + 1)
            self._conn.execute(
                "DELETE FROM playlist_items WHERE playlist_id = ?",
                (playlist_id,),
            )
            self._conn.executemany(
                """
                INSERT INTO playlist_items (playlist_id, position, track_id)
                VALUES (?, ?, ?)
                """,
                [
                    (playlist_id, idx, track_id)
                    for idx, track_id in enumerate(reordered)
                ],
            )
            self._conn.execute(
                "UPDATE playlists SET updated_at = ? WHERE playlist_id = ?",
                (int(time.time()), playlist_id),
            )
            self._conn.commit()

    def count(self, view: PlaylistView) -> int:
        query, params = self._build_count_query(view)
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return int(row["total"]) if row else 0

    def page(self, view: PlaylistView, offset: int, limit: int) -> list[TrackRow]:
        if limit <= 0:
            return []
        query, params = self._build_page_query(view, offset, limit)
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        result: list[TrackRow] = []
        for row in rows:
            result.append(
                TrackRow(
                    track_id=int(row["track_id"]),
                    path=Path(row["path"]),
                    title=row["title"],
                    artist=row["artist"],
                    album=row["album"],
                    duration_seconds=row["duration_seconds"],
                    has_metadata=bool(row["has_metadata"]),
                )
            )
        return result

    def get_track_path(self, track_id: int) -> Path:
        with self._lock:
            row = self._conn.execute(
                "SELECT path FROM tracks WHERE track_id = ?",
                (track_id,),
            ).fetchone()
        if not row:
            raise KeyError(f"track_id not found: {track_id}")
        return Path(row["path"])

    def get_track_id_for_path(self, path: Path) -> int | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT track_id FROM tracks WHERE path = ?",
                (str(path),),
            ).fetchone()
        return int(row["track_id"]) if row else None

    def list_paths(self, playlist_id: str) -> list[Path]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT tracks.path
                FROM playlist_items
                JOIN tracks ON tracks.track_id = playlist_items.track_id
                WHERE playlist_items.playlist_id = ?
                ORDER BY playlist_items.position
                """,
                (playlist_id,),
            ).fetchall()
        return [Path(row["path"]) for row in rows]

    def list_track_ids(self, playlist_id: str) -> list[int]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT track_id
                FROM playlist_items
                WHERE playlist_id = ?
                ORDER BY position
                """,
                (playlist_id,),
            ).fetchall()
        return [int(row["track_id"]) for row in rows]

    def get_position(self, view: PlaylistView, track_id: int) -> int | None:
        if view.sort_mode == "position" and not view.filter_text:
            with self._lock:
                row = self._conn.execute(
                    """
                    SELECT position FROM playlist_items
                    WHERE playlist_id = ? AND track_id = ?
                    """,
                    (view.playlist_id, track_id),
                ).fetchone()
            return int(row["position"]) if row else None
        query, params = self._build_position_query(view, track_id)
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return int(row["pos"]) if row else None

    def get_row_at(self, view: PlaylistView, position: int) -> TrackRow | None:
        rows = self.page(view, position, 1)
        return rows[0] if rows else None

    def get_row_by_track_id(self, track_id: int) -> TrackRow | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT tracks.track_id, tracks.path, metadata.title, metadata.artist,
                       metadata.album, metadata.duration_seconds,
                       metadata.track_id IS NOT NULL AS has_metadata
                FROM tracks
                LEFT JOIN metadata ON metadata.track_id = tracks.track_id
                WHERE tracks.track_id = ?
                """,
                (track_id,),
            ).fetchone()
        if not row:
            return None
        return TrackRow(
            track_id=int(row["track_id"]),
            path=Path(row["path"]),
            title=row["title"],
            artist=row["artist"],
            album=row["album"],
            duration_seconds=row["duration_seconds"],
            has_metadata=bool(row["has_metadata"]),
        )

    def fetch_metadata_if_valid(self, track_id: int, path: Path) -> TrackMeta | None:
        stat = self._stat_path(path)
        with self._lock:
            track_row = self._conn.execute(
                "SELECT mtime_ns, size_bytes FROM tracks WHERE track_id = ?",
                (track_id,),
            ).fetchone()
            if track_row is None:
                return None
            stored_mtime = int(track_row["mtime_ns"])
            stored_size = int(track_row["size_bytes"])
            if stat is None:
                if stored_mtime != -1 or stored_size != -1:
                    self._conn.execute(
                        """
                        UPDATE tracks SET mtime_ns = ?, size_bytes = ?
                        WHERE track_id = ?
                        """,
                        (-1, -1, track_id),
                    )
                    self._conn.execute(
                        "DELETE FROM metadata WHERE track_id = ?",
                        (track_id,),
                    )
                    self._conn.commit()
                return None
            if stored_mtime != stat.mtime_ns or stored_size != stat.size_bytes:
                self._conn.execute(
                    """
                    UPDATE tracks SET mtime_ns = ?, size_bytes = ?
                    WHERE track_id = ?
                    """,
                    (stat.mtime_ns, stat.size_bytes, track_id),
                )
                self._conn.execute(
                    "DELETE FROM metadata WHERE track_id = ?",
                    (track_id,),
                )
                self._conn.commit()
                return None
            meta_row = self._conn.execute(
                """
                SELECT title, artist, album, duration_seconds, extractor_version
                FROM metadata
                WHERE track_id = ?
                """,
                (track_id,),
            ).fetchone()
            if not meta_row:
                return None
            if meta_row["extractor_version"] != METADATA_EXTRACTOR_VERSION:
                self._conn.execute(
                    "DELETE FROM metadata WHERE track_id = ?",
                    (track_id,),
                )
                self._conn.commit()
                return None
        return TrackMeta(
            artist=meta_row["artist"],
            title=meta_row["title"],
            album=meta_row["album"],
            duration_seconds=meta_row["duration_seconds"],
        )

    def upsert_metadata(self, track_id: int, meta: TrackMeta) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO metadata (
                    track_id,
                    title,
                    artist,
                    album,
                    duration_seconds,
                    extracted_at,
                    extractor_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(track_id) DO UPDATE SET
                    title = excluded.title,
                    artist = excluded.artist,
                    album = excluded.album,
                    duration_seconds = excluded.duration_seconds,
                    extracted_at = excluded.extracted_at,
                    extractor_version = excluded.extractor_version
                """,
                (
                    track_id,
                    meta.title,
                    meta.artist,
                    meta.album,
                    meta.duration_seconds,
                    int(time.time()),
                    METADATA_EXTRACTOR_VERSION,
                ),
            )
            self._conn.commit()

    def _stat_path(self, path: Path) -> _PathStat | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return _PathStat(stat.st_mtime_ns, stat.st_size)

    def _upsert_track(self, path: Path) -> int | None:
        stat = self._stat_path(path)
        if stat is None:
            return None
        row = self._conn.execute(
            "SELECT track_id, mtime_ns, size_bytes FROM tracks WHERE path = ?",
            (str(path),),
        ).fetchone()
        if row:
            track_id = int(row["track_id"])
            if (
                int(row["mtime_ns"]) != stat.mtime_ns
                or int(row["size_bytes"]) != stat.size_bytes
            ):
                self._conn.execute(
                    """
                    UPDATE tracks SET mtime_ns = ?, size_bytes = ?
                    WHERE track_id = ?
                    """,
                    (stat.mtime_ns, stat.size_bytes, track_id),
                )
                self._conn.execute(
                    "DELETE FROM metadata WHERE track_id = ?",
                    (track_id,),
                )
            return track_id
        now = int(time.time())
        self._conn.execute(
            """
            INSERT INTO tracks (path, mtime_ns, size_bytes, added_at)
            VALUES (?, ?, ?, ?)
            """,
            (str(path), stat.mtime_ns, stat.size_bytes, now),
        )
        row = self._conn.execute(
            "SELECT track_id FROM tracks WHERE path = ?",
            (str(path),),
        ).fetchone()
        return int(row["track_id"]) if row else None

    def _apply_pragmas(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA busy_timeout = 3000")

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tracks (
                    track_id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL UNIQUE,
                    mtime_ns INTEGER NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    added_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (
                    track_id INTEGER PRIMARY KEY
                        REFERENCES tracks(track_id) ON DELETE CASCADE,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    duration_seconds REAL,
                    extracted_at INTEGER NOT NULL,
                    extractor_version TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS playlists (
                    playlist_id TEXT PRIMARY KEY,
                    name TEXT,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS playlist_items (
                    playlist_id TEXT NOT NULL
                        REFERENCES playlists(playlist_id) ON DELETE CASCADE,
                    position INTEGER NOT NULL,
                    track_id INTEGER NOT NULL
                        REFERENCES tracks(track_id) ON DELETE CASCADE,
                    PRIMARY KEY (playlist_id, position)
                );
                CREATE INDEX IF NOT EXISTS idx_tracks_path ON tracks(path);
                CREATE INDEX IF NOT EXISTS idx_playlist_items
                    ON playlist_items(playlist_id, position);
                CREATE INDEX IF NOT EXISTS idx_metadata_title ON metadata(title);
                CREATE INDEX IF NOT EXISTS idx_metadata_artist ON metadata(artist);
                """
            )
            self._conn.commit()

    def _ensure_playlist_locked(
        self, playlist_id: str, name: str | None, now: int
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO playlists (playlist_id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(playlist_id) DO UPDATE SET
                name = COALESCE(excluded.name, playlists.name),
                updated_at = excluded.updated_at
            """,
            (playlist_id, name, now, now),
        )

    def _build_count_query(self, view: PlaylistView) -> tuple[str, tuple[object, ...]]:
        base, params = self._build_base_query(view)
        query = f"SELECT COUNT(*) AS total {base}"
        return query, params

    def _build_page_query(
        self, view: PlaylistView, offset: int, limit: int
    ) -> tuple[str, tuple[object, ...]]:
        base, params = self._build_base_query(view)
        order_by = self._order_by_clause(view)
        query = (
            "SELECT tracks.track_id, tracks.path, metadata.title, metadata.artist, "
            "metadata.album, metadata.duration_seconds, "
            "metadata.track_id IS NOT NULL AS has_metadata "
            f"{base} {order_by} LIMIT ? OFFSET ?"
        )
        return query, params + (limit, offset)

    def _build_position_query(
        self, view: PlaylistView, track_id: int
    ) -> tuple[str, tuple[object, ...]]:
        base, params = self._build_base_query(view)
        order_by = self._order_by_clause(view)
        query = (
            "SELECT pos FROM ("
            "SELECT tracks.track_id AS track_id, "
            f"ROW_NUMBER() OVER ({order_by}) - 1 AS pos "
            f"{base}"
            ") WHERE track_id = ?"
        )
        return query, params + (track_id,)

    def _build_base_query(self, view: PlaylistView) -> tuple[str, tuple[object, ...]]:
        clause = (
            "FROM playlist_items "
            "JOIN tracks ON tracks.track_id = playlist_items.track_id "
            "LEFT JOIN metadata ON metadata.track_id = tracks.track_id "
            "WHERE playlist_items.playlist_id = ?"
        )
        params: list[object] = [view.playlist_id]
        if view.filter_text:
            filter_text = f"%{view.filter_text.strip().lower()}%"
            clause += (
                " AND ("
                "LOWER(COALESCE(metadata.title, '')) LIKE ? OR "
                "LOWER(COALESCE(metadata.artist, '')) LIKE ? OR "
                "LOWER(COALESCE(metadata.album, '')) LIKE ? OR "
                "LOWER(tracks.path) LIKE ?"
                ")"
            )
            params.extend([filter_text, filter_text, filter_text, filter_text])
        return clause, tuple(params)

    def _order_by_clause(self, view: PlaylistView) -> str:
        direction = "DESC" if view.sort_dir == "desc" else "ASC"
        if view.sort_mode == "title":
            primary = "LOWER(COALESCE(metadata.title, tracks.path))"
            secondary = "playlist_items.position"
        elif view.sort_mode == "artist":
            primary = "LOWER(COALESCE(metadata.artist, ''))"
            secondary = "LOWER(COALESCE(metadata.title, tracks.path))"
        elif view.sort_mode == "album":
            primary = "LOWER(COALESCE(metadata.album, ''))"
            secondary = "LOWER(COALESCE(metadata.title, tracks.path))"
        elif view.sort_mode == "duration":
            primary = "COALESCE(metadata.duration_seconds, 0)"
            secondary = "playlist_items.position"
        elif view.sort_mode == "path":
            primary = "LOWER(tracks.path)"
            secondary = "playlist_items.position"
        else:
            primary = "playlist_items.position"
            secondary = "playlist_items.position"
        return f"ORDER BY {primary} {direction}, {secondary} {direction}"


@dataclass(frozen=True)
class _PathStat:
    mtime_ns: int
    size_bytes: int
