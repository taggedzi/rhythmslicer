"""HackScope built-in visualization plugin."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Iterator

from rhythm_slicer.visualizations.host import VizContext

VIZ_NAME = "hackscope"


def _stable_seed(path: str) -> int:
    digest = sha256(path.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _format_duration(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    seconds = max(0, int(seconds))
    minutes, remainder = divmod(seconds, 60)
    return f"{minutes:02d}:{remainder:02d}"


def _meta_value(meta: dict, key: str) -> str | None:
    value = meta.get(key)
    if value is None:
        return None
    return str(value)


def _meta_int(meta: dict, key: str) -> int | None:
    value = meta.get(key)
    if isinstance(value, int):
        return value
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


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
) -> Iterator[str]:
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

        if (next(prng) % 5) == 0:
            noise = next(prng) & 0xFFFF
            log_lines.append(f">> jitter: {noise:04x}")

        left = [f"[HackScope] BREACHING ICE"] + [""] + log_lines
        right: list[str] = []
        if right_w > 0:
            right.append("ICE")
            right.append(f"{pct:3d}% [{_bar(pct, bar_w, fill='#', empty='-')}]")
            right.append("")
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
        yield frame


def _defrag_scene(
    stage_id: str,
    width: int,
    height: int,
    seed: int,
    *,
    frames: int = 36,
) -> Iterator[str]:
    """Flavor-only: old-school 'defrag' block consolidation."""
    prng = _lcg(seed ^ 0xD3F4A600)
    header = f"[HackScope] DEFRAG CACHE [{stage_id}]"

    grid_w = max(18, min(48, width - 2))
    grid_h = max(8, min(14, height - 6))

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
        out: list[str] = []
        sweep = step / max(1, frames - 1)
        for y in range(grid_h):
            row = cells[y * grid_w : (y + 1) * grid_w]

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
        lines.append(
            f"progress: {pct:3d}%  [{_bar(pct, max(10, min(40, width - 18)), fill='█', empty=' ')}]"
        )
        lines.append("")
        grid = render_grid(i)
        pad_left = max(0, (width - grid_w) // 2)
        for row in grid:
            lines.append((" " * pad_left) + row)
        lines.append("")
        lines.append("note: animation only (no real disk activity)")
        yield _pad_to_viewport(lines, width, height)


def _decrypt_scene(
    stage_id: str,
    meta: dict,
    width: int,
    height: int,
    seed: int,
    *,
    frames: int = 34,
) -> Iterator[str]:
    """Flavor-only: 'decrypt/extract' display using only real metadata."""
    prng = _lcg(seed ^ 0xDEC0DE99)
    title = _meta_value(meta, "title") or "Unknown"
    container = _meta_value(meta, "container") or "Unknown"
    codec = _meta_value(meta, "codec") or "Unknown"
    bitrate_kbps = _meta_int(meta, "bitrate_kbps")
    sample_rate = _meta_int(meta, "sample_rate_hz")
    channels = _meta_int(meta, "channels")

    bitrate = f"{bitrate_kbps} kbps" if bitrate_kbps else "Unknown"
    sample = f"{sample_rate} Hz" if sample_rate else "Unknown"
    channels_text = str(channels) if channels else "Unknown"

    base = [
        f">> container: {container}",
        f">> codec: {codec}",
        f">> bitrate: {bitrate}",
        f">> sample: {sample}",
        f">> channels: {channels_text}",
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
        yield _pad_to_viewport(lines, width, height)


def _render_dossier(
    track_path: str,
    meta: dict,
    viewport: tuple[int, int],
    prefs: dict,
) -> str:
    width, height = viewport
    show_absolute = bool(prefs.get("show_absolute_paths"))
    path = Path(track_path)
    path_label = str(path) if show_absolute else path.name

    title = _meta_value(meta, "title") or path.name
    artist = _meta_value(meta, "artist") or "Unknown"
    album = _meta_value(meta, "album") or "Unknown"
    duration = _format_duration(_meta_int(meta, "duration_sec")) or "Unknown"
    codec = _meta_value(meta, "codec") or "Unknown"
    container = _meta_value(meta, "container") or "Unknown"
    bitrate = _meta_int(meta, "bitrate_kbps")
    sample_rate = _meta_int(meta, "sample_rate_hz")
    channels = _meta_int(meta, "channels")

    lines = [
        "=== HACKSCRIPT DOSSIER ===",
        f"Title    : {title}",
        f"Artist   : {artist}",
        f"Album    : {album}",
        f"Path     : {path_label}",
        f"Length   : {duration}",
        f"Codec    : {codec}",
        f"Container: {container}",
        f"Bitrate  : {bitrate} kbps" if bitrate else "Bitrate  : Unknown",
        f"Sample   : {sample_rate} Hz" if sample_rate else "Sample   : Unknown",
        f"Channels : {channels}" if channels else "Channels : Unknown",
    ]
    return _pad_to_viewport(lines, width, height)


def generate_frames(ctx: VizContext) -> Iterator[str]:
    width = max(1, int(ctx.viewport_w))
    height = max(1, int(ctx.viewport_h))
    meta = ctx.meta if isinstance(ctx.meta, dict) else {}
    seed = ctx.seed if ctx.seed is not None else _stable_seed(ctx.track_path)
    stage_id = f"{seed:08x}"

    boot_lines = [
        f">> booting hackscript [{stage_id}]",
        ">> probing audio headers",
        ">> indexing metadata",
        ">> preparing hackscope scenes",
    ]
    for line in boot_lines:
        yield _pad_to_viewport([line], width, height)

    title = _meta_value(meta, "title") or Path(ctx.track_path).name
    yield from _ice_scene(
        stage_id,
        title,
        width,
        height,
        seed,
        frames=int(ctx.prefs.get("ice_frames", 30)),
    )
    yield from _defrag_scene(
        stage_id,
        width,
        height,
        seed,
        frames=int(ctx.prefs.get("defrag_frames", 36)),
    )
    yield from _decrypt_scene(
        stage_id,
        meta,
        width,
        height,
        seed,
        frames=int(ctx.prefs.get("decrypt_frames", 34)),
    )
    yield _render_dossier(ctx.track_path, meta, (width, height), ctx.prefs)
