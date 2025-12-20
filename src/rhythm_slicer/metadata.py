"""Audio metadata helpers for track display."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TrackMeta:
    artist: str | None
    title: str | None


_TRACK_META_CACHE: dict[Path, TrackMeta] = {}


def _extract_text(value: object | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "text"):
        try:
            value = value.text
        except Exception:
            value = value
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    if value is None:
        return None
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    text = text.strip()
    return text or None


def _read_tag(tags: object | None, keys: tuple[str, ...]) -> str | None:
    if tags is None:
        return None
    getter = getattr(tags, "get", None)
    if getter is None:
        return None
    for key in keys:
        try:
            value = getter(key)
        except Exception:
            continue
        text = _extract_text(value)
        if text:
            return text
    return None


def read_track_meta(path: Path) -> TrackMeta:
    """Best-effort metadata extraction with safe fallbacks."""
    try:
        from mutagen import File as MutagenFile
    except Exception:
        return TrackMeta(artist=None, title=None)
    try:
        audio = MutagenFile(path)
    except Exception:
        return TrackMeta(artist=None, title=None)
    if not audio:
        return TrackMeta(artist=None, title=None)
    tags = getattr(audio, "tags", None)
    artist = _read_tag(tags, ("artist", "ARTIST", "TPE1", "TPE2", "\xa9ART", "aART"))
    title = _read_tag(tags, ("title", "TITLE", "TIT2", "\xa9nam"))
    return TrackMeta(artist=artist, title=title)


def get_track_meta(path: Path) -> TrackMeta:
    cached = _TRACK_META_CACHE.get(path)
    if cached is not None:
        return cached
    meta = read_track_meta(path)
    _TRACK_META_CACHE[path] = meta
    return meta


def format_display_title(path: Path, meta: TrackMeta | None = None) -> str:
    if meta and meta.title:
        if meta.artist:
            return f"{meta.artist} – {meta.title}"
        return meta.title
    return path.name
