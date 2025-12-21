"""HackScript visualization host.

Design notes:
- "Truthful data only": metadata is sourced from the track file.
- No arbitrary code execution; visualization plugins are name-loaded only.
"""

from __future__ import annotations

from dataclasses import dataclass
import argparse
import json
from hashlib import sha256
from pathlib import Path
import sys
import time
from typing import Any, Iterator

from rhythm_slicer.visualizations.host import VizContext
from rhythm_slicer.visualizations.loader import load_viz
from rhythm_slicer.visualizations import minimal as minimal_viz


@dataclass(frozen=True)
class HackFrame:
    text: str
    hold_ms: int = 80
    mode: str = "hacking"


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


def _stable_seed(path: str) -> int:
    digest = sha256(path.encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _extract_metadata(track_path: Path) -> dict[str, Any]:
    try:
        from mutagen import File as MutagenFile
    except Exception:
        return {}
    try:
        audio = MutagenFile(track_path)
    except Exception:
        return {}
    if not audio:
        return {}

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

    meta: dict[str, Any] = {}
    if title:
        meta["title"] = title
    if artist:
        meta["artist"] = artist
    if album:
        meta["album"] = album
    if duration_sec is not None:
        meta["duration_sec"] = duration_sec
    if codec:
        meta["codec"] = codec
    if container:
        meta["container"] = container
    if bitrate_kbps is not None:
        meta["bitrate_kbps"] = bitrate_kbps
    if isinstance(sample_rate, int):
        meta["sample_rate_hz"] = sample_rate
    if isinstance(channels, int):
        meta["channels"] = channels
    return meta


def _build_context(
    track_path: Path,
    viewport: tuple[int, int],
    prefs: dict[str, Any],
    seed: int | None,
) -> VizContext:
    meta = _extract_metadata(track_path)
    width = max(1, int(viewport[0]))
    height = max(1, int(viewport[1]))
    seed_value = seed if seed is not None else _stable_seed(str(track_path))
    return VizContext(
        track_path=str(track_path),
        viewport_w=width,
        viewport_h=height,
        prefs=prefs,
        meta=meta,
        seed=seed_value,
    )


def run_generator(
    *,
    viz_name: str,
    track_path: Path,
    viewport: tuple[int, int],
    prefs: dict[str, Any],
    seed: int | None = None,
) -> Iterator[str]:
    try:
        plugin = load_viz(viz_name)
    except Exception as exc:
        print(
            f"warning: failed to load viz '{viz_name}': {exc}",
            file=sys.stderr,
        )
        plugin = minimal_viz
    if (
        getattr(plugin, "VIZ_NAME", None) != viz_name
        and viz_name != minimal_viz.VIZ_NAME
    ):
        print(
            f"warning: viz '{viz_name}' not found; using '{minimal_viz.VIZ_NAME}'",
            file=sys.stderr,
        )
    ctx = _build_context(track_path, viewport, prefs, seed)
    return plugin.generate_frames(ctx)


def generate(
    track_path: Path,
    viewport: tuple[int, int],
    prefs: dict[str, Any],
    seed: int | None = None,
    viz_name: str = "hackscope",
) -> Iterator[HackFrame]:
    fps = prefs.get("fps")
    if fps is None:
        hold_ms = 80
    else:
        try:
            fps_value = float(fps)
        except Exception:
            fps_value = 20.0
        fps_value = max(1.0, fps_value)
        hold_ms = int(1000 / fps_value)
    for frame in run_generator(
        viz_name=viz_name,
        track_path=track_path,
        viewport=viewport,
        prefs=prefs,
        seed=seed,
    ):
        yield HackFrame(text=frame, hold_ms=hold_ms)


def _parse_prefs(raw: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="HackScript visualization host")
    parser.add_argument("track_path", help="Path to audio file")
    parser.add_argument("--width", type=int, default=80, help="Viewport width")
    parser.add_argument("--height", type=int, default=24, help="Viewport height")
    parser.add_argument("--prefs", default="{}", help="JSON preferences object")
    parser.add_argument(
        "--pos-ms",
        type=int,
        default=None,
        help="Playback position in milliseconds",
    )
    parser.add_argument(
        "--state",
        choices=("playing", "paused"),
        default="playing",
        help="Playback state",
    )
    parser.add_argument("--seed", type=int, default=None, help="Seed override")
    parser.add_argument("--viz", default="hackscope", help="Visualization name")
    parser.add_argument("--fps", type=float, default=20.0, help="Frames per second")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    prefs = _parse_prefs(args.prefs)
    if args.pos_ms is not None:
        prefs["playback_pos_ms"] = args.pos_ms
    prefs["playback_state"] = args.state
    if "fps" not in prefs and args.fps:
        prefs["fps"] = args.fps
    viewport = (max(1, args.width), max(1, args.height))
    track = Path(args.track_path).expanduser()
    delay = 1.0 / max(1.0, float(prefs.get("fps", 20.0)))
    try:
        frames = run_generator(
            viz_name=args.viz,
            track_path=track,
            viewport=viewport,
            prefs=prefs,
            seed=args.seed,
        )
        for frame in frames:
            sys.stdout.write(frame + "\n")
            sys.stdout.flush()
            time.sleep(delay)
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
