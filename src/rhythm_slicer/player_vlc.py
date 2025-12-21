"""VLC-backed audio player."""

from __future__ import annotations

from typing import Any, Optional, cast
import threading

vlc: Any | None = None
_VLC_IMPORT_ERROR: Optional[Exception] = None


def _load_vlc() -> None:
    global vlc
    global _VLC_IMPORT_ERROR
    if vlc is not None or _VLC_IMPORT_ERROR is not None:
        return
    try:
        import vlc as vlc_module  # type: ignore
    except Exception as exc:  # pragma: no cover - platform-dependent import
        vlc = None
        _VLC_IMPORT_ERROR = exc
    else:
        vlc = cast(Any, vlc_module)
        _VLC_IMPORT_ERROR = None


class VlcPlayer:
    """Thin wrapper around python-vlc's MediaPlayer."""

    def __init__(self) -> None:
        _load_vlc()
        if vlc is None:
            raise RuntimeError(
                "VLC backend is unavailable. Install VLC and the python-vlc package."
            ) from _VLC_IMPORT_ERROR
        self._instance = cast(Any, vlc).Instance()
        self._player = self._instance.media_player_new()
        self._current_media: Optional[str] = None
        self._end_reached = threading.Event()
        self._attach_end_reached_event()

    def _attach_end_reached_event(self) -> None:
        if vlc is None:
            return
        vlc_module = cast(Any, vlc)
        try:
            event_manager = self._player.event_manager()
            event_manager.event_attach(
                vlc_module.EventType.MediaPlayerEndReached, self._handle_end_reached
            )
        except Exception:
            return

    def _handle_end_reached(self, event: object) -> None:
        del event
        self._end_reached.set()

    @property
    def current_media(self) -> Optional[str]:
        """Return the current media path if loaded."""
        return self._current_media

    def consume_end_reached(self) -> bool:
        """Return True if an end-reached event fired since last check."""
        if self._end_reached.is_set():
            self._end_reached.clear()
            return True
        return False

    def signal_end_reached(self) -> None:
        """Manually flag end reached (for tests)."""
        self._end_reached.set()

    def load(self, path: str) -> None:
        """Load media into the player."""
        media = self._instance.media_new(path)
        self._player.set_media(media)
        self._current_media = path
        self._end_reached.clear()

    def play(self) -> None:
        """Start playback."""
        self._player.play()

    def pause(self) -> None:
        """Pause playback."""
        self._player.pause()

    def stop(self) -> None:
        """Stop playback."""
        self._player.stop()

    def set_volume(self, volume: int) -> None:
        """Set volume (0-100)."""
        self._player.audio_set_volume(volume)

    def get_state(self) -> str:
        """Return a best-effort playback state string."""
        try:
            state = self._player.get_state()
        except Exception:
            return "unknown"
        if state is None:
            return "unknown"
        name = getattr(state, "name", None)
        if isinstance(name, str):
            return name.lower()
        return str(state).lower()

    def get_position_ms(self) -> Optional[int]:
        """Return the current playback position in ms, if available."""
        try:
            position = self._player.get_time()
        except Exception:
            return None
        if position is None or position < 0:
            return None
        return int(position)

    def get_length_ms(self) -> Optional[int]:
        """Return the media length in ms, if available."""
        try:
            length = self._player.get_length()
        except Exception:
            return None
        if length is None or length < 0:
            return None
        return int(length)

    def seek_ms(self, delta_ms: int) -> bool:
        """Seek relative to current position, returning success."""
        try:
            current = self._player.get_time()
        except Exception:
            return False
        if current is None or current < 0:
            return False
        target = max(0, int(current + delta_ms))
        try:
            self._player.set_time(target)
        except Exception:
            return False
        return True

    def set_position_ratio(self, ratio: float) -> bool:
        """Seek to an absolute position ratio between 0.0 and 1.0."""
        try:
            self._player.set_position(max(0.0, min(1.0, float(ratio))))
        except Exception:
            return False
        return True
