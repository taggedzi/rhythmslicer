"""Tests for HackScope render helpers."""

from __future__ import annotations

from pathlib import Path

from rhythm_slicer.visualizations import hackscope
from rhythm_slicer.visualizations.host import VizContext


def _ctx(*, prefs: dict | None = None, meta: dict | None = None) -> VizContext:
    return VizContext(
        track_path="song.mp3",
        viewport_w=40,
        viewport_h=10,
        prefs=prefs or {},
        meta=meta or {"title": "Song", "artist": "Artist"},
        seed=123,
    )


def _assert_frame(frame: str, width: int, height: int) -> None:
    lines = frame.splitlines()
    assert len(lines) == height
    assert all(len(hackscope._strip_sgr(line)) <= width for line in lines)


def test_format_bytes_and_file_facts(tmp_path: Path) -> None:
    assert hackscope._format_bytes(None) == "Unknown"
    assert hackscope._format_bytes(-1) == "Unknown"
    assert hackscope._format_bytes(512) == "512 B"
    assert hackscope._format_bytes(1024) == "1.0 KB"
    path = tmp_path / "song.mp3"
    path.write_bytes(b"abcd1234")
    facts = hackscope._file_facts(
        str(path),
        {"show_absolute_paths": False, "hackscope_hash_bytes": 4},
    )
    assert facts["path"] == path.name
    assert facts["size"] == "8 B"
    assert facts["hash_label"] == "sha256(first 4 bytes)"
    assert facts["hash"]
    missing = hackscope._file_facts(
        str(tmp_path / "missing.mp3"),
        {"show_absolute_paths": True, "hackscope_hash_bytes": 4},
    )
    assert missing["size"] is None
    assert missing["hash"] is None


def test_allocate_phases_and_locate_phase() -> None:
    phases = [("BOOT", 1.0), ("SCAN", 1.0)]
    allocation = hackscope._allocate_phases(5, phases)
    assert sum(allocation.values()) == 5
    allocation = hackscope._allocate_phases(3, phases, overrides={"BOOT": 5})
    assert sum(allocation.values()) == 3
    assert hackscope.locate_phase(10, []) == ("IDLE", 10)


def test_render_boot_and_defrag() -> None:
    ctx = _ctx()
    frame = hackscope.render_boot(ctx, "ABCD", 40, 10, local_i=1, phase_len=4)
    _assert_frame(frame, 40, 10)
    frame = hackscope.render_defrag("ABCD", 40, 10, seed=123, local_i=2, phase_len=5)
    _assert_frame(frame, 40, 10)


def test_render_ice_map_and_idle(monkeypatch) -> None:
    def fake_lcg(_seed: int):
        while True:
            yield 0

    monkeypatch.setattr(hackscope, "_lcg", fake_lcg)
    ctx = _ctx(prefs={"ansi_colors": True})
    frame = hackscope.render_ice(
        ctx,
        "ABCD",
        "Track",
        40,
        10,
        seed=123,
        local_i=1,
        phase_len=5,
        use_ansi=True,
    )
    _assert_frame(frame, 40, 10)
    frame = hackscope.render_map(
        ctx,
        "ABCD",
        {"title": "Song", "artist": "Artist", "codec": "mp3"},
        40,
        10,
        seed=123,
        local_i=2,
        phase_len=5,
        use_ansi=True,
    )
    _assert_frame(frame, 40, 10)
    frame = hackscope.render_idle(
        ctx,
        "ABCD",
        "song.mp3",
        {"title": "Song", "artist": "Artist"},
        40,
        10,
        seed=123,
        local_i=3,
        use_ansi=True,
    )
    _assert_frame(frame, 40, 10)


def test_render_decrypt_extract_scan_cover(monkeypatch, tmp_path: Path) -> None:
    def fake_lcg(_seed: int):
        while True:
            yield 0

    monkeypatch.setattr(hackscope, "_lcg", fake_lcg)
    ctx = _ctx()
    frame = hackscope.render_decrypt(
        ctx,
        "ABCD",
        {
            "title": "Song",
            "codec": "mp3",
            "container": "audio/mpeg",
            "bitrate_kbps": 192,
            "sample_rate_hz": 44100,
            "channels": 2,
        },
        40,
        10,
        seed=123,
        local_i=1,
        phase_len=5,
    )
    _assert_frame(frame, 40, 10)
    frame = hackscope.render_extract(
        ctx,
        "ABCD",
        {"title": "Song", "artist": "Artist", "album": "Album"},
        40,
        10,
        seed=123,
        local_i=2,
        phase_len=5,
    )
    _assert_frame(frame, 40, 10)
    track = tmp_path / "song.mp3"
    track.write_text("data", encoding="utf-8")
    facts = hackscope._file_facts(str(track), {"hackscope_hash_bytes": 2})
    frame = hackscope.render_scan(
        ctx,
        "ABCD",
        facts,
        40,
        10,
        seed=123,
        local_i=3,
        phase_len=5,
    )
    _assert_frame(frame, 40, 10)
    frame = hackscope.render_cover(
        ctx,
        "ABCD",
        {"title": "Song", "artist": "Artist", "codec": "mp3"},
        40,
        10,
        seed=123,
        local_i=4,
        phase_len=5,
    )
    _assert_frame(frame, 40, 10)


def test_render_ambient_lines() -> None:
    ctx = _ctx(prefs={"hackscope_ambient": True, "ansi_colors": True})
    lines = hackscope.render_ambient(ctx, global_frame=3, width=20, height=5, seed=123)
    assert len(lines) == 5
    assert all(len(line) == 20 for line in lines)
