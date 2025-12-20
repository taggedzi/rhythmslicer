"""HackScript frame generator for the visualizer pane."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class HackFrame:
    text: str
    hold_ms: int = 80
    mode: str = "hacking"


@dataclass(frozen=True)
class HackMeta:
    title: str | None
    artist: str | None
    album: str | None
    duration_sec: int | None
    codec: str | None
    container: str | None
    bitrate_kbps: int | None
    sample_rate_hz: int | None
    channels: int | None


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


def _format_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _stable_seed(path: Path) -> int:
    digest = sha256(str(path).encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _extract_metadata(track_path: Path) -> HackMeta:
    try:
        from mutagen import File as MutagenFile
    except Exception:
        return HackMeta(None, None, None, None, None, None, None, None, None)
    try:
        audio = MutagenFile(track_path)
    except Exception:
        return HackMeta(None, None, None, None, None, None, None, None, None)
    if not audio:
        return HackMeta(None, None, None, None, None, None, None, None, None)
    tags = getattr(audio, "tags", None)
    title = _read_tag(tags, ("title", "TITLE", "TIT2", "\xa9nam"))
    artist = _read_tag(tags, ("artist", "ARTIST", "TPE1", "TPE2", "\xa9ART", "aART"))
    album = _read_tag(tags, ("album", "ALBUM", "TALB", "\xa9alb"))
    info = getattr(audio, "info", None)
    duration_sec = None
    if info is not None:
        length = getattr(info, "length", None)
        if length is not None:
            try:
                duration_sec = int(length)
            except Exception:
                duration_sec = None
    bitrate_kbps = None
    if info is not None:
        bitrate = getattr(info, "bitrate", None)
        if bitrate:
            try:
                bitrate_kbps = int(bitrate // 1000)
            except Exception:
                bitrate_kbps = None
    sample_rate = None
    channels = None
    codec = None
    if info is not None:
        sample_rate = getattr(info, "sample_rate", None)
        channels = getattr(info, "channels", None)
        codec = _extract_text(getattr(info, "codec", None))
    container = None
    mime = getattr(audio, "mime", None)
    if isinstance(mime, (list, tuple)) and mime:
        container = _extract_text(mime[0])
    if container is None:
        container = _extract_text(track_path.suffix.lstrip(".")) or None
    if codec is None and container:
        codec = container.split("/")[-1]
    return HackMeta(
        title=title,
        artist=artist,
        album=album,
        duration_sec=duration_sec,
        codec=codec,
        container=container,
        bitrate_kbps=bitrate_kbps,
        sample_rate_hz=sample_rate if isinstance(sample_rate, int) else None,
        channels=channels if isinstance(channels, int) else None,
    )


def _clip_lines(lines: list[str], width: int, height: int) -> list[str]:
    if width <= 0 or height <= 0:
        return []
    clipped: list[str] = []
    for line in lines[:height]:
        line = line[:width] if len(line) > width else line
        clipped.append(line)
    if not clipped:
        clipped.append("")
    return clipped[:height]


def _render_dossier(
    track_path: Path,
    meta: HackMeta,
    viewport: tuple[int, int],
    prefs: dict,
) -> str:
    width, height = viewport
    show_absolute = bool(prefs.get("show_absolute_paths"))
    path_label = str(track_path) if show_absolute else track_path.name
    title = meta.title or track_path.name
    artist = meta.artist or "Unknown"
    album = meta.album or "Unknown"
    duration = _format_duration(meta.duration_sec) or "Unknown"
    codec = meta.codec or "Unknown"
    container = meta.container or "Unknown"
    bitrate = f"{meta.bitrate_kbps} kbps" if meta.bitrate_kbps else "Unknown"
    sample = (
        f"{meta.sample_rate_hz} Hz" if meta.sample_rate_hz else "Unknown"
    )
    channels = str(meta.channels) if meta.channels else "Unknown"
    lines = [
        "=== HACKSCRIPT DOSSIER ===",
        f"Title   : {title}",
        f"Artist  : {artist}",
        f"Album   : {album}",
        f"Path    : {path_label}",
        f"Length  : {duration}",
        f"Codec   : {codec}",
        f"Container: {container}",
        f"Bitrate : {bitrate}",
        f"Sample  : {sample}",
        f"Channels: {channels}",
    ]
    clipped = _clip_lines(lines, width, height)
    return "\n".join(line[:width] for line in clipped)


def generate(
    track_path: Path,
    viewport: tuple[int, int],
    prefs: dict,
    seed: int | None = None,
) -> Iterator[HackFrame]:
    width, height = viewport
    width = max(1, width)
    height = max(1, height)
    meta = _extract_metadata(track_path)
    seed = seed if seed is not None else _stable_seed(track_path)
    stage_id = f"{seed:08x}"
    hacking_lines = [
        f">> booting hackscript [{stage_id}]",
        ">> probing audio headers",
        ">> indexing metadata",
        ">> compiling dossier",
    ]
    for line in hacking_lines:
        clipped = _clip_lines([line], width, height)
        yield HackFrame(text="\n".join(clipped))
    dossier = _render_dossier(track_path, meta, (width, height), prefs)
    yield HackFrame(text=dossier, hold_ms=400)
