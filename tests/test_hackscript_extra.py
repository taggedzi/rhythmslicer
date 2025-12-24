"""Additional tests for hackscript helpers."""

from __future__ import annotations

from pathlib import Path
import builtins

from types import SimpleNamespace

from rhythm_slicer import hackscript


class _TextValue:
    def __init__(self, value: object, *, raises: bool = False) -> None:
        self._value = value
        self._raises = raises

    @property
    def text(self) -> object:
        if self._raises:
            raise RuntimeError("boom")
        return self._value

    def __str__(self) -> str:
        return "fallback"


class _Tags:
    def __init__(self, mapping: dict[str, object], *, raises: set[str] | None = None):
        self._mapping = mapping
        self._raises = raises or set()

    def get(self, key: str) -> object:
        if key in self._raises:
            raise KeyError(key)
        return self._mapping.get(key)


def test_extract_text_handles_common_types() -> None:
    assert hackscript._extract_text(None) is None
    assert hackscript._extract_text(b"  hello ") == "hello"
    assert hackscript._extract_text(["  hi  "]) == "hi"
    assert hackscript._extract_text(_TextValue("  tag  ")) == "tag"


def test_read_tag_selects_first_valid() -> None:
    tags = _Tags({"b": ["  value  "]}, raises={"a"})
    assert hackscript._read_tag(tags, ("a", "b")) == "value"


def test_parse_prefs_handles_invalid_json() -> None:
    assert hackscript._parse_prefs("") == {}
    assert hackscript._parse_prefs("{bad") == {}
    assert hackscript._parse_prefs("[1, 2]") == {}
    assert hackscript._parse_prefs('{"ok": 1}') == {"ok": 1}


def test_build_context_normalizes_viewport(monkeypatch) -> None:
    monkeypatch.setattr(hackscript, "_extract_metadata", lambda _: {"title": "x"})
    monkeypatch.setattr(hackscript, "_stable_seed", lambda _: 99)
    ctx = hackscript._build_context(
        Path("song.mp3"),
        viewport=(0, -5),
        prefs={"fps": 10},
        seed=None,
    )
    assert ctx.viewport_w == 1
    assert ctx.viewport_h == 1
    assert ctx.seed == 99
    assert ctx.meta == {"title": "x"}


def test_generate_uses_fps_for_hold_ms(monkeypatch) -> None:
    monkeypatch.setattr(hackscript, "run_generator", lambda **_: iter(["a", "b"]))
    frames = list(
        hackscript.generate(
            track_path=Path("song.mp3"),
            viewport=(10, 4),
            prefs={"fps": 10},
        )
    )
    assert [frame.hold_ms for frame in frames] == [100, 100]


def test_generate_invalid_fps_defaults(monkeypatch) -> None:
    monkeypatch.setattr(hackscript, "run_generator", lambda **_: iter(["x"]))
    frame = next(
        hackscript.generate(
            track_path=Path("song.mp3"),
            viewport=(10, 4),
            prefs={"fps": "nope"},
        )
    )
    assert frame.hold_ms == 50


def test_run_generator_falls_back_to_minimal(monkeypatch, caplog) -> None:
    def boom(_: str):
        raise RuntimeError("missing")

    monkeypatch.setattr(hackscript, "load_viz", boom)
    monkeypatch.setattr(hackscript, "_extract_metadata", lambda _: {})
    caplog.set_level("WARNING")
    frames = hackscript.run_generator(
        viz_name="missing",
        track_path=Path("song.mp3"),
        viewport=(20, 4),
        prefs={},
        seed=1,
    )
    assert "RhythmSlicer" in next(frames)
    assert "Failed to load viz 'missing'" in caplog.text


def test_run_generator_warns_on_mismatch(monkeypatch, caplog) -> None:
    plugin = SimpleNamespace(
        VIZ_NAME="other",
        generate_frames=lambda ctx: iter(["frame"]),
    )
    monkeypatch.setattr(hackscript, "load_viz", lambda _: plugin)
    monkeypatch.setattr(hackscript, "_extract_metadata", lambda _: {})
    caplog.set_level("WARNING")
    frames = hackscript.run_generator(
        viz_name="custom",
        track_path=Path("song.mp3"),
        viewport=(20, 4),
        prefs={},
        seed=1,
    )
    assert next(frames) == "frame"
    assert "Viz 'custom' not found" in caplog.text


def test_extract_metadata_full(monkeypatch, tmp_path: Path) -> None:
    class FakeInfo:
        length = 123.4
        bitrate = 256000
        sample_rate = 44100
        channels = 2
        codec = b"mp3"

    class FakeAudio:
        def __init__(self) -> None:
            self.tags = {
                "title": ["Title"],
                "artist": ["Artist"],
                "album": ["Album"],
            }
            self.info = FakeInfo()
            self.mime = ["audio/mpeg"]

    def fake_file(path: Path):
        return FakeAudio()

    monkeypatch.setitem(
        hackscript.sys.modules, "mutagen", SimpleNamespace(File=fake_file)
    )
    track_path = tmp_path / "song.mp3"
    meta = hackscript._extract_metadata(track_path)
    assert meta["title"] == "Title"
    assert meta["artist"] == "Artist"
    assert meta["album"] == "Album"
    assert meta["duration_sec"] == 123
    assert meta["bitrate_kbps"] == 256
    assert meta["sample_rate_hz"] == 44100
    assert meta["channels"] == 2
    assert meta["container"] == "audio/mpeg"
    assert meta["codec"] == "mp3"


def test_extract_metadata_handles_errors(monkeypatch, caplog, tmp_path: Path) -> None:
    def fake_file(path: Path):
        raise RuntimeError("bad")

    monkeypatch.setitem(
        hackscript.sys.modules, "mutagen", SimpleNamespace(File=fake_file)
    )
    caplog.set_level("WARNING")
    meta = hackscript._extract_metadata(tmp_path / "song.mp3")
    assert meta == {}
    assert "Failed to read metadata" in caplog.text


def test_extract_metadata_logs_missing_mutagen(
    monkeypatch, caplog, tmp_path: Path
) -> None:
    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mutagen":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    caplog.set_level("WARNING")
    meta = hackscript._extract_metadata(tmp_path / "song.mp3")
    assert meta == {}
    assert "mutagen is not installed" in caplog.text


def test_main_writes_frames(monkeypatch, capsys) -> None:
    captured: dict[str, object] = {}

    def fake_run_generator(**kwargs):
        captured.update(kwargs)
        return iter(["frame"])

    monkeypatch.setattr(hackscript, "run_generator", fake_run_generator)
    monkeypatch.setattr(hackscript.time, "sleep", lambda _: None)
    code = hackscript.main(
        [
            "song.mp3",
            "--width",
            "10",
            "--height",
            "3",
            "--prefs",
            '{"foo": 1}',
            "--pos-ms",
            "500",
            "--state",
            "paused",
            "--seed",
            "7",
            "--viz",
            "minimal",
            "--fps",
            "10",
        ]
    )
    assert code == 0
    assert capsys.readouterr().out.strip() == "frame"
    prefs = captured["prefs"]
    assert prefs["playback_pos_ms"] == 500
    assert prefs["playback_state"] == "paused"
    assert prefs["fps"] == 10.0


def test_main_handles_keyboard_interrupt(monkeypatch) -> None:
    def fake_run_generator(**_):
        def _gen():
            raise KeyboardInterrupt
            yield "x"

        return _gen()

    monkeypatch.setattr(hackscript, "run_generator", fake_run_generator)
    code = hackscript.main(["song.mp3"])
    assert code == 130
