"""HackScript frame generator for the visualizer pane.

Design notes:
- "Truthful data only": This generator only uses real track metadata + file path info.
- Any "hacking" animations are purely flavor, deterministic, and MUST NOT imply real security actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Public data structures
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Metadata helpers (mutagen-owned)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

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


def _pad_to_viewport(lines: list[str], width: int, height: int) -> str:
    """Return a full-screen frame (exactly height lines, each <= width chars)."""
    width = max(1, width)
    height = max(1, height)
    clipped = _clip_lines(lines, width, height)
    # Right-pad to avoid visual jitter when the player reuses old chars
    padded = [(ln + (" " * (width - len(ln))))[:width] for ln in clipped]
    while len(padded) < height:
        padded.append(" " * width)
    return "\n".join(padded[:height])


def _render_two_col(
    left: list[str],
    right: list[str],
    width: int,
    height: int,
    *,
    split: int | None = None,
) -> str:
    """Render two columns with a single space gutter."""
    width = max(1, width)
    height = max(1, height)
    gutter = 1 if width >= 3 else 0
    if split is None:
        split = max(10, (width * 2) // 3)
    split = max(1, min(width, split))
    left_w = max(1, min(width, split))
    right_w = max(0, width - left_w - gutter)

    out: list[str] = []
    for i in range(height):
        l = left[i] if i < len(left) else ""
        r = right[i] if i < len(right) else ""
        l = (l + (" " * (left_w - len(l))))[:left_w]
        if right_w > 0:
            r = (r + (" " * (right_w - len(r))))[:right_w]
            out.append(l + (" " * gutter) + r)
        else:
            out.append(l)
    return "\n".join(out)


def _bar(pct: int, width: int, *, fill: str = "█", empty: str = "░") -> str:
    width = max(1, width)
    pct = max(0, min(100, pct))
    fill_n = int((pct / 100) * width)
    return (fill * fill_n) + (empty * (width - fill_n))


# ---------------------------------------------------------------------------
# Deterministic "flavor" animations (seeded)
# ---------------------------------------------------------------------------

def _lcg(seed: int) -> Iterator[int]:
    """Simple deterministic PRNG (no external deps)."""
    x = seed & 0xFFFFFFFF
    while True:
        x = (1664525 * x + 1013904223) & 0xFFFFFFFF
        yield x


def _ice_scene(
    stage_id: str,
    title: str,
    width: int,
    height: int,
    seed: int,
    *,
    frames: int = 30,
) -> Iterator[HackFrame]:
    """Flavor-only: 'ICE' breach display."""
    prng = _lcg(seed ^ 0x1CEB00DA)
    left_w = max(1, min(width, (width * 2) // 3))
    right_w = max(0, width - left_w - (1 if width >= 3 else 0))
    bar_w = max(8, right_w - 6) if right_w > 0 else max(12, width - 18)

    base_log = [
        f">> target: {title}",
        f">> session: {stage_id}",
        ">> link: establish",
        ">> probe: perimeter",
        ">> ice: detect",
        ">> ice: map nodes",
        ">> ice: bypass vector: timing skew",
        ">> priv: elevate (simulated)",
        ">> status: ok",
    ]

    for i in range(frames):
        pct = int((i / max(1, frames - 1)) * 100)
        shown = 2 + (i * len(base_log) // max(1, frames - 1))
        log_lines = base_log[: min(len(base_log), shown)]

        # Add a tiny deterministic "packet" noise line sometimes (pure flavor)
        if (next(prng) % 5) == 0:
            noise = next(prng) & 0xFFFF
            log_lines.append(f">> jitter: {noise:04x}")

        left = [f"[HackScope] BREACHING ICE"] + [""] + log_lines
        right: list[str] = []
        if right_w > 0:
            right.append("ICE")
            right.append(f"{pct:3d}% [{_bar(pct, bar_w, fill='#', empty='-')}]")
            right.append("")
            # Mini lattice
            lattice_h = max(6, min(10, height - 6))
            lattice_w = max(10, min(right_w, 18))
            sweep = i % max(1, lattice_w - 2)
            for y in range(lattice_h):
                row = []
                for x in range(lattice_w):
                    if x in (0, lattice_w - 1) or y in (0, lattice_h - 1):
                        row.append("+")
                    elif x == 1 + sweep:
                        row.append("*")
                    else:
                        row.append(".")
                right.append("".join(row))
        frame = _render_two_col(left, right, width, height)
        yield HackFrame(text=frame, hold_ms=80)


def _defrag_scene(
    stage_id: str,
    width: int,
    height: int,
    seed: int,
    *,
    frames: int = 36,
) -> Iterator[HackFrame]:
    """Flavor-only: old-school 'defrag' block consolidation."""
    prng = _lcg(seed ^ 0xD3F4A600)
    header = f"[HackScope] DEFRAG CACHE [{stage_id}]"

    # Grid size chosen to be stable across resize while staying readable.
    grid_w = max(18, min(48, width - 2))
    grid_h = max(8, min(14, height - 6))

    # Create a starting fragmented map deterministically.
    cells = []
    for _ in range(grid_w * grid_h):
        r = next(prng) % 100
        if r < 55:
            cells.append("·")
        elif r < 85:
            cells.append("▒")
        else:
            cells.append("█")

    def render_grid(step: int) -> list[str]:
        # "Consolidate" by moving █ and ▒ toward the left over time (pure animation).
        # We do this by sorting each row with a changing key.
        out: list[str] = []
        sweep = step / max(1, frames - 1)
        for y in range(grid_h):
            row = cells[y * grid_w : (y + 1) * grid_w]
            # Bias increases with sweep
            def key(ch: str) -> int:
                if ch == "█":
                    return 0
                if ch == "▒":
                    return 1 if sweep < 0.6 else 0
                return 2

            row2 = sorted(row, key=key)
            out.append("".join(row2))
        return out

    for i in range(frames):
        pct = int((i / max(1, frames - 1)) * 100)
        lines: list[str] = [header, ""]
        lines.append(f"progress: {pct:3d}%  [{_bar(pct, max(10, min(40, width - 18)), fill='█', empty=' ')}]")
        lines.append("")
        grid = render_grid(i)
        # Center-ish
        pad_left = max(0, (width - grid_w) // 2)
        for row in grid:
            lines.append((" " * pad_left) + row)
        lines.append("")
        lines.append("note: animation only (no real disk activity)")
        yield HackFrame(text=_pad_to_viewport(lines, width, height), hold_ms=80)


def _decrypt_scene(
    stage_id: str,
    meta: HackMeta,
    width: int,
    height: int,
    seed: int,
    *,
    frames: int = 34,
) -> Iterator[HackFrame]:
    """Flavor-only: 'decrypt/extract' display using only real metadata."""
    prng = _lcg(seed ^ 0xDEC0DE99)
    title = meta.title or "Unknown"
    container = meta.container or "Unknown"
    codec = meta.codec or "Unknown"
    bitrate = f"{meta.bitrate_kbps} kbps" if meta.bitrate_kbps else "Unknown"
    sample = f"{meta.sample_rate_hz} Hz" if meta.sample_rate_hz else "Unknown"
    channels = str(meta.channels) if meta.channels else "Unknown"

    base = [
        f">> container: {container}",
        f">> codec: {codec}",
        f">> bitrate: {bitrate}",
        f">> sample: {sample}",
        f">> channels: {channels}",
        ">> payload: locate",
        ">> keyslot: derive (simulated)",
        ">> decrypt: stream start (simulated)",
        ">> extract: ok (simulated)",
        ">> cleanup: traces (simulated)",
    ]

    for i in range(frames):
        pct = int((i / max(1, frames - 1)) * 100)
        shown = 1 + (i * len(base) // max(1, frames - 1))
        log = base[:shown]

        # Occasionally add a deterministic "block id" line (flavor)
        if (next(prng) % 6) == 0:
            blk = next(prng) & 0xFFFF
            log.append(f">> block: {blk:04x}")

        lines: list[str] = [
            f"[HackScope] DECRYPT / EXTRACT [{stage_id}]",
            f"track: {title}",
            "",
            f"progress: {pct:3d}%  [{_bar(pct, max(10, min(40, width - 18)), fill='█', empty='░')}]",
            "",
            *log,
        ]
        lines.append("")
        lines.append("note: animation only (metadata-driven)")
        yield HackFrame(text=_pad_to_viewport(lines, width, height), hold_ms=80)


# ---------------------------------------------------------------------------
# Dossier (truthful, metadata-driven)
# ---------------------------------------------------------------------------

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
    sample = f"{meta.sample_rate_hz} Hz" if meta.sample_rate_hz else "Unknown"
    channels = str(meta.channels) if meta.channels else "Unknown"

    lines = [
        "=== HACKSCRIPT DOSSIER ===",
        f"Title    : {title}",
        f"Artist   : {artist}",
        f"Album    : {album}",
        f"Path     : {path_label}",
        f"Length   : {duration}",
        f"Codec    : {codec}",
        f"Container: {container}",
        f"Bitrate  : {bitrate}",
        f"Sample   : {sample}",
        f"Channels : {channels}",
    ]
    return _pad_to_viewport(lines, width, height)


# ---------------------------------------------------------------------------
# Public generator entrypoint
# ---------------------------------------------------------------------------

def generate(
    track_path: Path,
    viewport: tuple[int, int],
    prefs: dict,
    seed: int | None = None,
) -> Iterator[HackFrame]:
    width, height = viewport
    width = max(1, int(width))
    height = max(1, int(height))

    meta = _extract_metadata(track_path)
    seed = seed if seed is not None else _stable_seed(track_path)
    stage_id = f"{seed:08x}"

    # Boot / probe lines (your existing behavior)
    boot_lines = [
        f">> booting hackscript [{stage_id}]",
        ">> probing audio headers",
        ">> indexing metadata",
        ">> preparing hackscope scenes",
    ]
    for line in boot_lines:
        yield HackFrame(text=_pad_to_viewport([line], width, height))

    # NEW: mini-displays (flavor-only, deterministic)
    title = meta.title or track_path.name
    yield from _ice_scene(stage_id, title, width, height, seed, frames=int(prefs.get("ice_frames", 30)))
    yield from _defrag_scene(stage_id, width, height, seed, frames=int(prefs.get("defrag_frames", 36)))
    yield from _decrypt_scene(stage_id, meta, width, height, seed, frames=int(prefs.get("decrypt_frames", 34)))

    # Dossier (truthful)
    yield HackFrame(text=_render_dossier(track_path, meta, (width, height), prefs), hold_ms=400)
