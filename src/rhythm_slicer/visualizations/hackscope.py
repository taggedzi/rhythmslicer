"""HackScope built-in visualization plugin."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import os
import re
from typing import Iterator

from rhythm_slicer.visualizations.host import VizContext

VIZ_NAME = "hackscope"

_SGR_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_ANSI_RESET = "\x1b[0m"
_ANSI_DIM = "\x1b[2m"
_ANSI_CYAN = "\x1b[36m"
_ANSI_GREEN = "\x1b[32m"
_ANSI_YELLOW = "\x1b[33m"
_ANSI_MAGENTA = "\x1b[35m"
_ANSI_RED = "\x1b[31m"


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


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _clip_lines(lines: list[str], width: int, height: int) -> list[str]:
    if width <= 0 or height <= 0:
        return []
    clipped: list[str] = []
    for line in lines[:height]:
        clipped.append(line)
    if not clipped:
        clipped.append("")
    return clipped[:height]


def _pad_to_viewport(lines: list[str], width: int, height: int) -> str:
    """Return a full-screen frame (exactly height lines, each <= width chars)."""
    width = max(1, width)
    height = max(1, height)
    clipped = _clip_lines(lines, width, height)
    padded = [_pad_line(ln, width) for ln in clipped]
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
        l = _pad_line(l, left_w)
        if right_w > 0:
            r = _pad_line(r, right_w)
            out.append(l + (" " * gutter) + r)
        else:
            out.append(l)
    return "\n".join(out)


def _bar(pct: int, width: int, *, fill: str = "█", empty: str = "░") -> str:
    width = max(1, width)
    pct = max(0, min(100, pct))
    fill_n = int((pct / 100) * width)
    return (fill * fill_n) + (empty * (width - fill_n))


def _color(text: str, code: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{code}{text}{_ANSI_RESET}"


def _strip_sgr(text: str) -> str:
    return _SGR_PATTERN.sub("", text)


def _truncate_ansi(text: str, width: int) -> str:
    if width <= 0:
        return ""
    parts = _SGR_PATTERN.split(text)
    codes = _SGR_PATTERN.findall(text)
    out: list[str] = []
    remaining = width
    for idx, chunk in enumerate(parts):
        if remaining <= 0:
            break
        if chunk:
            take = min(len(chunk), remaining)
            out.append(chunk[:take])
            remaining -= take
        if idx < len(codes):
            out.append(codes[idx])
    return "".join(out)


def _pad_line(text: str, width: int) -> str:
    if width <= 0:
        return ""
    visible = len(_strip_sgr(text))
    if visible > width:
        return _truncate_ansi(text, width)
    if visible < width:
        return text + (" " * (width - visible))
    return text


def _allocate_phases(
    total_frames: int,
    phases: list[tuple[str, float]],
    overrides: dict[str, int] | None = None,
) -> dict[str, int]:
    overrides = overrides or {}
    total_frames = max(total_frames, len(phases))
    allocation: dict[str, int] = {}
    remaining = total_frames
    for name, _weight in phases:
        if name in overrides:
            count = max(1, overrides[name])
            allocation[name] = count
            remaining -= count
    remaining = max(0, remaining)
    weights = {name: weight for name, weight in phases if name not in overrides}
    weight_sum = sum(weights.values()) or 1.0
    for name, weight in weights.items():
        allocation[name] = max(1, int(remaining * (weight / weight_sum)))
    # Adjust to exact total
    current_total = sum(allocation.values())
    while current_total < total_frames:
        name = max(weights, key=weights.get) if weights else phases[0][0]
        allocation[name] = allocation.get(name, 0) + 1
        current_total += 1
    while current_total > total_frames and allocation:
        name = max(allocation, key=allocation.get)
        if allocation[name] > 1:
            allocation[name] -= 1
            current_total -= 1
        else:
            break
    return allocation


def locate_phase(
    global_frame: int, phases: list[tuple[str, int]]
) -> tuple[str, int]:
    remaining = max(0, int(global_frame))
    for name, count in phases:
        if remaining < count:
            return name, remaining
        remaining -= count
    if phases:
        name, count = phases[-1]
        return name, max(0, count - 1)
    return "IDLE", remaining


def _lcg(seed: int) -> Iterator[int]:
    """Simple deterministic PRNG (no external deps)."""
    x = seed & 0xFFFFFFFF
    while True:
        x = (1664525 * x + 1013904223) & 0xFFFFFFFF
        yield x


def _format_bytes(size: int | None) -> str:
    if size is None or size < 0:
        return "Unknown"
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{int(size)} B"


def _file_facts(track_path: str, prefs: dict) -> dict[str, str | None]:
    facts: dict[str, str | None] = {
        "size": None,
        "path": None,
        "hash_label": None,
        "hash": None,
    }
    show_absolute = bool(prefs.get("show_absolute_paths"))
    path = Path(track_path)
    facts["path"] = str(path) if show_absolute else path.name
    try:
        size = os.stat(path).st_size
        facts["size"] = _format_bytes(size)
    except Exception:
        facts["size"] = None
    hash_bytes = _safe_int(prefs.get("hackscope_hash_bytes", 0), 0)
    if hash_bytes > 0:
        try:
            with path.open("rb") as handle:
                data = handle.read(hash_bytes)
            digest = sha256(data).hexdigest()
            facts["hash_label"] = f"sha256(first {len(data)} bytes)"
            facts["hash"] = digest
        except Exception:
            facts["hash_label"] = f"sha256(first {hash_bytes} bytes)"
            facts["hash"] = None
    return facts


def _frame_seed(base_seed: int, phase_name: str, local_i: int) -> int:
    digest = sha256(f"{base_seed}:{phase_name}:{local_i}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def render_boot(
    stage_id: str,
    width: int,
    height: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    header = _color("[HackScope]", _ANSI_CYAN, use_ansi)
    boot_lines = [
        f">> booting hackscript [{stage_id}]",
        ">> probing audio headers",
        ">> indexing metadata",
        ">> preparing hackscope scenes",
    ]
    total = max(1, phase_len)
    line = boot_lines[local_i % len(boot_lines)]
    pct = int((local_i / max(1, total - 1)) * 100)
    bar = _color(
        _bar(pct, max(10, min(30, width - 20)), fill="#", empty="-"),
        _ANSI_GREEN,
        use_ansi,
    )
    lines = [
        f"{header} BOOT [{stage_id}]",
        "",
        line,
        "",
        f"{_color('progress', _ANSI_DIM, use_ansi)}: {pct:3d}% [{bar}]",
    ]
    return _pad_to_viewport(lines, width, height)


def render_ice(
    stage_id: str,
    title: str,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    """Flavor-only: 'ICE' breach display."""
    prng = _lcg(_frame_seed(seed, "ICE", local_i))
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

    total = max(1, phase_len)
    pct = int((local_i / max(1, total - 1)) * 100)
    shown = 2 + (local_i * len(base_log) // max(1, total - 1))
    log_lines = base_log[: min(len(base_log), shown)]

    if (next(prng) % 5) == 0:
        noise = next(prng) & 0xFFFF
        log_lines.append(f">> jitter: {noise:04x}")

    header = _color("[HackScope]", _ANSI_CYAN, use_ansi)
    left = [f"{header} BREACHING ICE"] + [""] + log_lines
    right: list[str] = []
    if right_w > 0:
        right.append(_color("ICE", _ANSI_CYAN, use_ansi))
        bar = _bar(pct, bar_w, fill="#", empty="-")
        bar = _color(bar, _ANSI_GREEN, use_ansi)
        right.append(f"{pct:3d}% [{bar}]")
        right.append("")
        lattice_h = max(6, min(10, height - 6))
        lattice_w = max(10, min(right_w, 18))
        sweep = local_i % max(1, lattice_w - 2)
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
    return _render_two_col(left, right, width, height)


def render_map(
    stage_id: str,
    meta: dict,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    prng = _lcg(_frame_seed(seed, "MAP", local_i))
    left_w = max(1, min(width, (width * 2) // 3))
    right_w = max(0, width - left_w - (1 if width >= 3 else 0))
    lattice_h = max(6, min(10, height - 6))
    lattice_w = (
        max(10, min(right_w, 18)) if right_w > 0 else max(10, min(width, 18))
    )
    nodes = []
    for _ in range(8):
        x = 1 + (next(prng) % max(1, lattice_w - 2))
        y = 1 + (next(prng) % max(1, lattice_h - 2))
        nodes.append((x, y))

    title = _meta_value(meta, "title") or "Unknown"
    artist = _meta_value(meta, "artist") or "Unknown"
    album = _meta_value(meta, "album") or "Unknown"
    codec = _meta_value(meta, "codec") or "Unknown"
    container = _meta_value(meta, "container") or "Unknown"
    sample = _meta_int(meta, "sample_rate_hz")
    channels = _meta_int(meta, "channels")
    sample_text = f"{sample} Hz" if sample else "Unknown"
    channels_text = str(channels) if channels else "Unknown"

    base_log = [
        ">> mapping nodes (simulated)",
        ">> enumerating ports (simulated)",
        f">> title: {title}",
        f">> artist: {artist}",
        f">> album: {album}",
        f">> codec: {codec}",
        f">> container: {container}",
        f">> sample: {sample_text}",
        f">> channels: {channels_text}",
    ]
    header = _color("[HackScope]", _ANSI_CYAN, use_ansi)
    total = max(1, phase_len)
    pct = int((local_i / max(1, total - 1)) * 100)
    shown = 2 + (local_i * len(base_log) // max(1, total - 1))
    log_lines = base_log[: min(len(base_log), shown)]
    left = [f"{header} MAP / TOPOLOGY [{stage_id}]"] + [""] + log_lines
    right: list[str] = []
    if right_w > 0:
        right.append(_color("MAP", _ANSI_CYAN, use_ansi))
        bar = _color(
            _bar(pct, max(8, right_w - 6), fill="#", empty="-"),
            _ANSI_GREEN,
            use_ansi,
        )
        right.append(f"{pct:3d}% [{bar}]")
        right.append("")
        sweep = local_i % max(1, lattice_w - 2)
        lit = max(1, int((local_i / max(1, total - 1)) * len(nodes)))
        for y in range(lattice_h):
            row = []
            for x in range(lattice_w):
                if x in (0, lattice_w - 1) or y in (0, lattice_h - 1):
                    row.append("+")
                elif x == 1 + sweep:
                    row.append("*")
                elif (x, y) in nodes[:lit]:
                    node = "o"
                    row.append(_color(node, _ANSI_MAGENTA, use_ansi))
                else:
                    row.append(".")
            right.append("".join(row))
    return _render_two_col(left, right, width, height)


def render_defrag(
    stage_id: str,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    """Flavor-only: old-school 'defrag' block consolidation."""
    prng = _lcg(_frame_seed(seed, "DEFRAG", local_i))
    header = f"{_color('[HackScope]', _ANSI_CYAN, use_ansi)} DEFRAG CACHE [{stage_id}]"

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

    def render_grid(step: int, total: int) -> list[str]:
        out: list[str] = []
        sweep = step / max(1, total - 1)
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

    total = max(1, phase_len)
    pct = int((local_i / max(1, total - 1)) * 100)
    lines: list[str] = [header, ""]
    bar = _bar(pct, max(10, min(40, width - 18)), fill="█", empty=" ")
    bar = _color(bar, _ANSI_GREEN, use_ansi)
    lines.append(f"{_color('progress', _ANSI_DIM, use_ansi)}: {pct:3d}%  [{bar}]")
    lines.append("")
    grid = render_grid(local_i, total)
    pad_left = max(0, (width - grid_w) // 2)
    for row in grid:
        lines.append((" " * pad_left) + row)
    lines.append("")
    note = _color("note", _ANSI_DIM, use_ansi)
    lines.append(f"{note}: animation only (no real disk activity)")
    return _pad_to_viewport(lines, width, height)


def render_decrypt(
    stage_id: str,
    meta: dict,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    """Flavor-only: 'decrypt/extract' display using only real metadata."""
    prng = _lcg(_frame_seed(seed, "DECRYPT", local_i))
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

    total = max(1, phase_len)
    pct = int((local_i / max(1, total - 1)) * 100)
    shown = 1 + (local_i * len(base) // max(1, total - 1))
    log = base[:shown]

    if (next(prng) % 6) == 0:
        blk = next(prng) & 0xFFFF
        log.append(f">> block: {blk:04x}")

    header = f"{_color('[HackScope]', _ANSI_CYAN, use_ansi)} DECRYPT / EXTRACT [{stage_id}]"
    progress_bar = _bar(pct, max(10, min(40, width - 18)), fill="█", empty="░")
    progress_bar = _color(progress_bar, _ANSI_GREEN, use_ansi)
    lines: list[str] = [
        header,
        f"{_color('track', _ANSI_DIM, use_ansi)}: {title}",
        "",
        f"{_color('progress', _ANSI_DIM, use_ansi)}: {pct:3d}%  [{progress_bar}]",
        "",
        *log,
    ]
    lines.append("")
    note = _color("note", _ANSI_DIM, use_ansi)
    lines.append(f"{note}: animation only (metadata-driven)")
    return _pad_to_viewport(lines, width, height)


def render_extract(
    stage_id: str,
    meta: dict,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    prng = _lcg(_frame_seed(seed, "EXTRACT", local_i))
    title = _meta_value(meta, "title") or "Unknown"
    artist = _meta_value(meta, "artist") or "Unknown"
    album = _meta_value(meta, "album") or "Unknown"
    base = [
        f">> title: {title}",
        f">> artist: {artist}",
        f">> album: {album}",
        ">> extract: verified (simulated)",
        ">> checksum: ok (simulated)",
    ]
    header = f"{_color('[HackScope]', _ANSI_CYAN, use_ansi)} EXTRACT / VERIFY [{stage_id}]"
    total = max(1, phase_len)
    pct = int((local_i / max(1, total - 1)) * 100)
    shown = 1 + (local_i * len(base) // max(1, total - 1))
    log = base[:shown]
    bar = _color(
        _bar(pct, max(10, min(40, width - 18)), fill="█", empty="░"),
        _ANSI_GREEN,
        use_ansi,
    )
    lines = [
        header,
        f"{_color('track', _ANSI_DIM, use_ansi)}: {title}",
        "",
        f"{_color('progress', _ANSI_DIM, use_ansi)}: {pct:3d}%  [{bar}]",
        "",
        *log,
    ]
    if (next(prng) % 7) == 0:
        lines.append(">> verify: pass")
    lines.append("")
    note = _color("note", _ANSI_DIM, use_ansi)
    lines.append(f"{note}: animation only (metadata-driven)")
    return _pad_to_viewport(lines, width, height)


def render_scan(
    stage_id: str,
    facts: dict[str, str | None],
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    prng = _lcg(_frame_seed(seed, "SCAN", local_i))
    header = f"{_color('[HackScope]', _ANSI_CYAN, use_ansi)} SCAN / FILE FACTS [{stage_id}]"
    total = max(1, phase_len)
    size = facts.get("size") or "Unknown"
    path = facts.get("path") or "Unknown"
    hash_label = facts.get("hash_label")
    hash_value = facts.get("hash")
    base = [
        f">> size: {size}",
        f">> path: {path}",
    ]
    if hash_label:
        base.append(f">> {hash_label}: {hash_value or 'Unavailable'}")
    base.append(">> scan: ok (simulated)")
    pct = int((local_i / max(1, total - 1)) * 100)
    shown = 1 + (local_i * len(base) // max(1, total - 1))
    log = base[:shown]
    if (next(prng) % 6) == 0:
        log.append(">> fsync: ok (simulated)")
    bar = _color(
        _bar(pct, max(10, min(40, width - 18)), fill="█", empty="░"),
        _ANSI_GREEN,
        use_ansi,
    )
    lines = [
        header,
        "",
        f"{_color('progress', _ANSI_DIM, use_ansi)}: {pct:3d}%  [{bar}]",
        "",
        *log,
    ]
    lines.append("")
    note = _color("note", _ANSI_DIM, use_ansi)
    lines.append(f"{note}: animation only (file facts)")
    return _pad_to_viewport(lines, width, height)


def render_cover(
    stage_id: str,
    meta: dict,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    prng = _lcg(_frame_seed(seed, "COVER", local_i))
    title = _meta_value(meta, "title") or "Unknown"
    artist = _meta_value(meta, "artist") or "Unknown"
    codec = _meta_value(meta, "codec") or "Unknown"
    container = _meta_value(meta, "container") or "Unknown"
    header = f"{_color('[HackScope]', _ANSI_CYAN, use_ansi)} COVER TRACKS [{stage_id}]"
    total = max(1, phase_len)
    pct = int((local_i / max(1, total - 1)) * 100)
    scrub = _bar(pct, max(10, min(40, width - 18)), fill="=", empty="-")
    scrub = _color(scrub, _ANSI_MAGENTA, use_ansi)
    lines = [
        header,
        "",
        f"{_color('redacting', _ANSI_DIM, use_ansi)}: {pct:3d}% [{scrub}]",
        "",
        f">> summary: {title}",
        f">> artist: {artist}",
        f">> codec: {codec}",
        f">> container: {container}",
    ]
    if (next(prng) % 5) == 0:
        lines.append(">> logs: scrubbed (simulated)")
    lines.append("")
    note = _color("note", _ANSI_DIM, use_ansi)
    lines.append(f"{note}: animation only (metadata summary)")
    return _pad_to_viewport(lines, width, height)


def render_dossier(
    track_path: str,
    meta: dict,
    viewport: tuple[int, int],
    prefs: dict,
    local_i: int,
    phase_len: int,
    *,
    use_ansi: bool = False,
) -> str:
    del local_i, phase_len
    return _render_dossier(
        track_path,
        meta,
        viewport,
        prefs,
        use_ansi=use_ansi,
    )


def render_idle(
    stage_id: str,
    track_path: str,
    meta: dict,
    width: int,
    height: int,
    seed: int,
    local_i: int,
    *,
    use_ansi: bool = False,
) -> str:
    prng = _lcg(_frame_seed(seed, "IDLE", local_i))
    title = _meta_value(meta, "title") or Path(track_path).name
    artist = _meta_value(meta, "artist") or "Unknown"
    spinner = "|/-\\"
    status_lines = [
        "idle: monitoring playback",
        "idle: maintaining session",
        "idle: await next phase",
    ]
    spin = spinner[local_i % len(spinner)]
    status = status_lines[local_i % len(status_lines)]
    header = f"{_color('[HackScope]', _ANSI_CYAN, use_ansi)} IDLE [{stage_id}] {spin}"
    lines = [
        header,
        "",
        f"{_color('now playing', _ANSI_DIM, use_ansi)}: {title}",
        f"{_color('artist', _ANSI_DIM, use_ansi)}: {artist}",
        "",
        f"{_color('status', _ANSI_DIM, use_ansi)}: {status}",
    ]
    if (next(prng) % 7) == 0:
        lines.append(">> heartbeat: ok")
    lines.append("")
    note = _color("note", _ANSI_DIM, use_ansi)
    lines.append(f"{note}: idle loop (visual only)")
    return _pad_to_viewport(lines, width, height)


def _render_dossier(
    track_path: str,
    meta: dict,
    viewport: tuple[int, int],
    prefs: dict,
    *,
    use_ansi: bool = False,
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

    heading = _color("=== HACKSCRIPT DOSSIER ===", _ANSI_CYAN, use_ansi)
    label = lambda text: _color(text, _ANSI_DIM, use_ansi)
    lines = [
        heading,
        f"{label('Title')}    : {title}",
        f"{label('Artist')}   : {artist}",
        f"{label('Album')}    : {album}",
        f"{label('Path')}     : {path_label}",
        f"{label('Length')}   : {duration}",
        f"{label('Codec')}    : {codec}",
        f"{label('Container')}: {container}",
        f"{label('Bitrate')}  : {bitrate} kbps" if bitrate else f"{label('Bitrate')}  : Unknown",
        f"{label('Sample')}   : {sample_rate} Hz" if sample_rate else f"{label('Sample')}   : Unknown",
        f"{label('Channels')} : {channels}" if channels else f"{label('Channels')} : Unknown",
    ]
    return _pad_to_viewport(lines, width, height)


def generate_frames(ctx: VizContext) -> Iterator[str]:
    width = max(1, int(ctx.viewport_w))
    height = max(1, int(ctx.viewport_h))
    meta = ctx.meta if isinstance(ctx.meta, dict) else {}
    use_ansi = bool(ctx.prefs.get("ansi_colors", True))
    seed = ctx.seed if ctx.seed is not None else _stable_seed(ctx.track_path)
    stage_id = f"{seed:08x}"
    duration_sec = _safe_int(meta.get("duration_sec", 0), 0)
    coverage = _safe_float(ctx.prefs.get("hackscope_coverage", 0.85), 0.85)
    min_show = _safe_int(ctx.prefs.get("hackscope_min_show_sec", 45), 45)
    max_show = _safe_int(ctx.prefs.get("hackscope_max_show_sec", 8 * 60), 8 * 60)
    if duration_sec <= 0:
        show_seconds = min_show
    else:
        show_seconds = _clamp_int(int(duration_sec * coverage), min_show, max_show)
    fps = max(1.0, _safe_float(ctx.prefs.get("fps", 20.0), 20.0))
    total_frames = max(1, int(show_seconds * fps))
    start_ms = int(ctx.prefs.get("playback_pos_ms", 0) or 0)
    start_frame = max(0, int((start_ms / 1000.0) * fps))

    phases = [
        ("BOOT", 0.03),
        ("ICE", 0.14),
        ("MAP", 0.12),
        ("DEFRAG", 0.12),
        ("SCAN", 0.12),
        ("DECRYPT", 0.18),
        ("EXTRACT", 0.12),
        ("COVER", 0.07),
        ("DOSSIER", 0.10),
    ]
    overrides: dict[str, int] = {}
    if "ice_frames" in ctx.prefs:
        overrides["ICE"] = _safe_int(ctx.prefs.get("ice_frames", 0), 0)
    if "defrag_frames" in ctx.prefs:
        overrides["DEFRAG"] = _safe_int(ctx.prefs.get("defrag_frames", 0), 0)
    if "decrypt_frames" in ctx.prefs:
        overrides["DECRYPT"] = _safe_int(ctx.prefs.get("decrypt_frames", 0), 0)
    phase_frames = _allocate_phases(total_frames, phases, overrides)
    phase_list = [(name, phase_frames[name]) for name, _weight in phases]
    phase_len_map = {name: count for name, count in phase_list}
    total_scripted = sum(count for _name, count in phase_list)
    facts = _file_facts(ctx.track_path, ctx.prefs)
    title = _meta_value(meta, "title") or Path(ctx.track_path).name

    global_frame = start_frame
    while True:
        if global_frame < total_scripted:
            phase_name, local_i = locate_phase(global_frame, phase_list)
            phase_len = phase_len_map.get(phase_name, 1)
            if phase_name == "BOOT":
                frame = render_boot(
                    stage_id,
                    width,
                    height,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "ICE":
                frame = render_ice(
                    stage_id,
                    title,
                    width,
                    height,
                    seed,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "MAP":
                frame = render_map(
                    stage_id,
                    meta,
                    width,
                    height,
                    seed,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "DEFRAG":
                frame = render_defrag(
                    stage_id,
                    width,
                    height,
                    seed,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "SCAN":
                frame = render_scan(
                    stage_id,
                    facts,
                    width,
                    height,
                    seed,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "DECRYPT":
                frame = render_decrypt(
                    stage_id,
                    meta,
                    width,
                    height,
                    seed,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "EXTRACT":
                frame = render_extract(
                    stage_id,
                    meta,
                    width,
                    height,
                    seed,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "COVER":
                frame = render_cover(
                    stage_id,
                    meta,
                    width,
                    height,
                    seed,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            elif phase_name == "DOSSIER":
                frame = render_dossier(
                    ctx.track_path,
                    meta,
                    (width, height),
                    ctx.prefs,
                    local_i,
                    phase_len,
                    use_ansi=use_ansi,
                )
            else:
                frame = render_idle(
                    stage_id,
                    ctx.track_path,
                    meta,
                    width,
                    height,
                    seed,
                    local_i,
                    use_ansi=use_ansi,
                )
        else:
            idle_i = global_frame - total_scripted
            frame = render_idle(
                stage_id,
                ctx.track_path,
                meta,
                width,
                height,
                seed,
                idle_i,
                use_ansi=use_ansi,
            )
        yield frame
        global_frame += 1
