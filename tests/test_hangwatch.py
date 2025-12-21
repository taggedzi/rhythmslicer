"""Tests for hangwatch helpers."""

from __future__ import annotations

import io

from rhythm_slicer import hangwatch


def test_enable_faulthandler_creates_hangdump(tmp_path, monkeypatch) -> None:
    calls: list[object] = []

    def fake_enable(*, file, all_threads: bool) -> None:
        calls.append((file, all_threads))

    monkeypatch.setattr(hangwatch.faulthandler, "enable", fake_enable)
    log_path = tmp_path / "app.log"
    hang_path = hangwatch.enable_faulthandler(log_path)
    assert hang_path.name == "hangdump.log"
    assert hang_path.parent == tmp_path
    assert calls
    handle = hangwatch._HANG_FILE
    assert handle is not None
    handle.close()
    hangwatch._HANG_FILE = None
    hangwatch._HANG_PATH = None


def test_dump_threads_writes_header(monkeypatch) -> None:
    buffer = io.StringIO()

    def fake_dump_traceback(*, file, all_threads: bool) -> None:
        file.write("traceback")

    monkeypatch.setattr(hangwatch.faulthandler, "dump_traceback", fake_dump_traceback)
    hangwatch._HANG_FILE = buffer
    hangwatch.dump_threads("test")
    output = buffer.getvalue()
    assert "test" in output
    assert "traceback" in output
    hangwatch._HANG_FILE = None
    hangwatch._HANG_PATH = None


def test_watchdog_triggers_dump(monkeypatch) -> None:
    calls: list[str] = []

    def fake_dump(label: str) -> None:
        calls.append(label)

    class _Stop:
        def __init__(self) -> None:
            self._set = False

        def is_set(self) -> bool:
            return self._set

        def set(self) -> None:
            self._set = True

        def wait(self, _seconds: float) -> bool:
            self._set = True
            return True

    monkeypatch.setattr(hangwatch, "dump_threads", fake_dump)
    monkeypatch.setattr(hangwatch.time, "monotonic", lambda: 100.0)
    watchdog = hangwatch.HangWatchdog(lambda: 0.0, threshold_seconds=1.0)
    watchdog._stop_event = _Stop()
    watchdog._run()
    assert calls == ["hang detected"]
