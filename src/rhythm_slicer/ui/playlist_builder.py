"""Playlist builder screen for RhythmSlicer."""

from __future__ import annotations

from dataclasses import dataclass
import multiprocessing
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue as MPQueue
from pathlib import Path
import queue
import threading
from typing import Callable, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Button, Static

from rhythm_slicer.metadata import format_display_title, get_cached_track_meta
from rhythm_slicer.playlist import Playlist, Track
from rhythm_slicer.playlist_builder import (
    build_track_from_path,
    is_hidden_or_system,
    reorder_items,
    run_collect_audio_files,
)
from rhythm_slicer.playlist_io import save_m3u8
from rhythm_slicer.ui.file_browser import FileBrowserWidget
from rhythm_slicer.ui.marquee import Marquee
from rhythm_slicer.ui.metadata_loader import MetadataLoader
from rhythm_slicer.ui.virtual_playlist_list import (
    VirtualPlaylistList,
    VirtualPlaylistScrollbar,
)


@dataclass
class _ScanState:
    scan_id: int
    process: BaseProcess
    queue: MPQueue
    reader_thread: threading.Thread
    cancel_requested: bool = False


@dataclass
class _ScanProgress:
    dirs: int = 0
    files: int = 0
    found: int = 0
    path: str = ""


class PlaylistBuilderScreen(Screen):
    """Two-pane playlist builder inspired by Midnight Commander."""

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._start_path = start_path
        self._file_browser: Optional[FileBrowserWidget] = None
        self._playlist_list: Optional[VirtualPlaylistList] = None
        self._scan_states: dict[int, _ScanState] = {}
        self._active_scan_id: int | None = None
        self._scan_id_counter = 0
        self._scan_progress: _ScanProgress | None = None
        self._scan_spinner_timer: Timer | None = None
        self._scan_spinner_index = 0
        self._scan_spinner_frames = ["|", "/", "-", "\\"]
        self._scan_status_text = ""
        self._pending_commit_scan_id: int | None = None
        self._deferred_playlist_update = False
        self._meta_loader = MetadataLoader(max_workers=2, queue_limit=100)
        self._meta_generation = 0
        self._meta_timer: Timer | None = None
        self._playlist_scrollbar: VirtualPlaylistScrollbar | None = None

    def compose(self) -> ComposeResult:
        with Container(id="builder_root"):
            with Horizontal(id="builder_panes"):
                yield _panel_wrapper(
                    "Files",
                    Vertical(
                        FileBrowserWidget(self._start_path, id="builder_file_browser"),
                        Horizontal(
                            Button("Add", id="builder_files_add"),
                            Button("Cancel", id="builder_files_cancel", disabled=True),
                            id="builder_files_actions",
                        ),
                        Static("", id="builder_scan_status"),
                        id="builder_left_stack",
                    ),
                    panel_id="builder_left_panel",
                )
                yield _panel_wrapper(
                    "Playlist",
                    Vertical(
                        Horizontal(
                            Button("Save", id="builder_playlist_save"),
                            Button("Load", id="builder_playlist_load"),
                            Static("", id="builder_playlist_header_spacer"),
                            Button("Done", id="builder_done"),
                            id="builder_playlist_header",
                        ),
                        Marquee("", id="builder_playlist_details"),
                        Horizontal(
                            VirtualPlaylistList(id="builder_playlist"),
                            VirtualPlaylistScrollbar(id="builder_playlist_scrollbar"),
                            id="builder_playlist_body",
                        ),
                        Horizontal(
                            Button(
                                "Select All",
                                id="builder_playlist_select_all",
                            ),
                            Button("Remove", id="builder_playlist_remove"),
                            Button("Clear", id="builder_playlist_clear"),
                            Static("", id="builder_playlist_actions_spacer"),
                            Button("↑", id="builder_playlist_move_up"),
                            Button("↓", id="builder_playlist_move_down"),
                            id="builder_playlist_actions",
                        ),
                        id="builder_right_stack",
                    ),
                    panel_id="builder_right_panel",
                )

    def on_mount(self) -> None:
        self._file_browser = self.query_one("#builder_file_browser", FileBrowserWidget)
        self._playlist_list = self.query_one(
            "#builder_playlist", VirtualPlaylistList
        )
        self._playlist_scrollbar = self.query_one(
            "#builder_playlist_scrollbar", VirtualPlaylistScrollbar
        )
        self._refresh_playlist_entries()
        self._set_scan_status_visible(False)
        self._start_metadata_loader()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "builder_files_add":
            if not self._file_browser:
                return
            selected = self._file_browser.selected_path
            if selected:
                if is_hidden_or_system(selected, include_parents=True):
                    self._confirm_hidden_add([selected])
                else:
                    self._start_add_scan([selected])
            return
        if button_id == "builder_files_cancel":
            self._cancel_active_scan()
            return
        if button_id == "builder_playlist_select_all":
            if self._playlist_list:
                self._playlist_list.check_all()
            return
        if button_id == "builder_playlist_remove":
            self.action_remove_from_playlist()
            return
        if button_id == "builder_playlist_clear":
            if self._playlist_list:
                self._playlist_list.clear_checked()
            return
        if button_id == "builder_playlist_move_up":
            self._move_selected_tracks("up")
            return
        if button_id == "builder_playlist_move_down":
            self._move_selected_tracks("down")
            return
        if button_id == "builder_playlist_save":
            self._save_playlist(force_prompt=False)
            return
        if button_id == "builder_playlist_load":
            self._load_playlist()
            return
        if button_id == "builder_done":
            self.app.pop_screen()
            return

    def on_key(self, event: events.Key) -> None:
        key = event.key
        if key == "enter":
            focused = self.app.focused
            if isinstance(focused, Button):
                focused.press()
                event.stop()
                return
        if key in {"pageup", "pagedown"}:
            event.stop()
            return
        if key == "escape":
            if self._active_scan_id is not None:
                self._cancel_active_scan()
            else:
                self.app.pop_screen()
            event.stop()
            return
        focused = getattr(self, "focused", None)
        if not self._is_playlist_focus(focused):
            return
        if key == "space":
            self._toggle_playlist_selection()
            event.stop()
            return
        if key == "enter":
            event.stop()
            return
        if key == "d":
            self.action_remove_from_playlist()
            event.stop()
            return
        if key == "u":
            self._move_selected_tracks("up")
            event.stop()
            return
        if key == "j":
            self._move_selected_tracks("down")
            event.stop()
            return
        if key == "s":
            self._save_playlist(force_prompt=False)
            event.stop()
            return
        if key in {"S", "shift+s"}:
            self._save_playlist(force_prompt=True)
            event.stop()
            return
        if key == "l":
            self._load_playlist()
            event.stop()
            return

    def _is_playlist_focus(self, focused: object | None) -> bool:
        if focused is self._playlist_list:
            return True
        playlist_ids = {
            "builder_playlist_save",
            "builder_playlist_load",
            "builder_done",
            "builder_playlist_select_all",
            "builder_playlist_remove",
            "builder_playlist_clear",
            "builder_playlist_move_up",
            "builder_playlist_move_down",
        }
        current = focused
        while current is not None:
            if getattr(current, "id", None) in playlist_ids:
                return True
            current = getattr(current, "parent", None)
        return False

    def _refresh_playlist_entries(self) -> None:
        if not self._playlist_list:
            return
        playlist = self._ensure_playlist()
        self._playlist_list.set_tracks(playlist.tracks)
        self._meta_generation += 1
        self._meta_loader.set_generation(self._meta_generation)
        if playlist.tracks:
            self._update_playlist_details(self._focused_playlist_index())
        else:
            self._clear_playlist_details()

    def _playlist_display_title(self, track: Track) -> str:
        meta = get_cached_track_meta(track.path)
        if meta:
            return format_display_title(track.path, meta)
        if track.title and track.title != track.path.stem:
            return track.title
        return track.path.name

    def _playlist_details_text(self, track: Track) -> str:
        title = self._playlist_display_title(track)
        return f"{title} ({track.path})"

    def _clear_playlist_details(self) -> None:
        self.query_one("#builder_playlist_details", Marquee).set_text("")

    def _update_playlist_details(self, index: Optional[int]) -> None:
        playlist = self._ensure_playlist()
        if index is None or index < 0 or index >= len(playlist.tracks):
            self._clear_playlist_details()
            return
        details = self._playlist_details_text(playlist.tracks[index])
        self.query_one("#builder_playlist_details", Marquee).set_text(details)

    def _focused_playlist_index(self) -> Optional[int]:
        if not self._playlist_list:
            return None
        if not self._playlist_list:
            return None
        return self._playlist_list.cursor_index

    def _toggle_playlist_selection(self) -> None:
        if self._playlist_list:
            self._playlist_list.toggle_checked_at_cursor()

    def _remove_selected_tracks(self) -> None:
        playlist = self._ensure_playlist()
        if playlist.is_empty():
            return
        tracks = getattr(playlist, "tracks", None)
        if not isinstance(tracks, list):
            raise RuntimeError(
                "PlaylistBuilderScreen expected playlist.tracks to be a list."
            )
        selected_indices = self._selected_or_focused_indices()
        valid_indices = {
            index for index in selected_indices if 0 <= index < len(tracks)
        }
        if not valid_indices:
            return
        cursor_index = self._focused_playlist_index() or 0
        playing_index = self._valid_playing_index(len(tracks))
        original_count = len(tracks)
        removed_indices = sorted(valid_indices, reverse=True)
        removed_set = set(removed_indices)
        for index in removed_indices:
            playlist.remove(index)
        if self._playlist_list:
            self._playlist_list.clear_checked()
        self._reconcile_playing_index_after_remove(
            playing_index,
            removed_set,
            original_count,
        )
        playlist.clamp_index()
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()
        self._restore_playlist_cursor(cursor_index)

    def action_remove_from_playlist(self) -> None:
        self._remove_selected_tracks()

    def _selected_or_focused_indices(self) -> set[int]:
        if self._playlist_list:
            checked = self._playlist_list.get_checked_indices()
            if checked:
                return set(checked)
        focused = self._focused_playlist_index()
        if focused is None:
            return set()
        return {focused}

    def _valid_playing_index(self, track_count: int) -> Optional[int]:
        playing_index = getattr(self.app, "_playing_index", None)
        if playing_index is None:
            return None
        if 0 <= playing_index < track_count:
            return playing_index
        return None

    def _reconcile_playing_index_after_remove(
        self,
        playing_index: Optional[int],
        removed_indices: set[int],
        original_count: int,
    ) -> None:
        if playing_index is None:
            return
        if playing_index not in removed_indices:
            shift = sum(1 for index in removed_indices if index < playing_index)
            setattr(self.app, "_playing_index", playing_index - shift)
            return
        remaining = original_count - len(removed_indices)
        if remaining <= 0:
            self._stop_playback_for_empty_playlist()
            return
        candidate = playing_index
        if candidate >= remaining:
            candidate = remaining - 1
        setattr(self.app, "_playing_index", candidate)

    def _stop_playback_for_empty_playlist(self) -> None:
        stop_action = getattr(self.app, "action_stop", None)
        if callable(stop_action):
            stop_action()
            return
        player = getattr(self.app, "player", None)
        if player is not None and hasattr(player, "stop"):
            player.stop()
        if hasattr(self.app, "_stop_hackscript"):
            self.app._stop_hackscript()
        setattr(self.app, "_playing_index", None)

    def _restore_playlist_cursor(self, preferred_index: int) -> None:
        if not self._playlist_list:
            return
        if not self._ensure_playlist().tracks:
            return
        self._playlist_list.set_cursor_index(preferred_index)
        self._update_playlist_details(self._focused_playlist_index())

    def _move_selected_tracks(self, direction: str) -> None:
        playlist = self._ensure_playlist()
        if playlist.is_empty():
            return
        selection = set(self._playlist_list.get_checked_indices()) if self._playlist_list else set()
        if not selection:
            # No selection means move the cursor row by default.
            focused = self._focused_playlist_index()
            if focused is None:
                return
            selection = {focused}
        playing_path = self._current_playing_path()
        reordered, new_selection = reorder_items(
            playlist.tracks,
            selection,
            "up" if direction == "up" else "down",
        )
        playlist.tracks = reordered
        if self._playlist_list:
            self._playlist_list.set_tracks(playlist.tracks)
            self._playlist_list.set_checked_indices(new_selection)
        self._reconcile_playing_index(playing_path)
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()
        if self._playlist_list and new_selection:
            self._playlist_list.set_cursor_index(min(new_selection))

    def _save_playlist(self, *, force_prompt: bool) -> None:
        playlist = self._ensure_playlist()
        if playlist.is_empty():
            return
        if force_prompt or not getattr(self.app, "_last_playlist_path", None):
            if hasattr(self.app, "run_worker") and hasattr(
                self.app, "_save_playlist_flow"
            ):
                self.app.run_worker(self.app._save_playlist_flow(), exclusive=True)
            return
        dest = getattr(self.app, "_last_playlist_path")
        if not dest:
            return
        try:
            save_m3u8(playlist, dest, mode="auto")
        except Exception:
            return
        if hasattr(self.app, "_set_message"):
            self.app._set_message(f"Saved playlist: {dest}")

    def _load_playlist(self) -> None:
        if hasattr(self.app, "run_worker") and hasattr(self.app, "_load_playlist_flow"):
            self.app.run_worker(self._load_playlist_worker(), exclusive=True)

    async def _load_playlist_worker(self) -> None:
        load_flow = getattr(self.app, "_load_playlist_flow", None)
        if not callable(load_flow):
            return
        await load_flow()
        if self._playlist_list:
            self._playlist_list.clear_checked()
        self._refresh_playlist_entries()

    def _refresh_playlist_after_edit(self) -> None:
        if hasattr(self.app, "_reset_play_order"):
            self.app._reset_play_order()
        if hasattr(self.app, "_sync_play_order_pos"):
            self.app._sync_play_order_pos()
        if hasattr(self.app, "_update_playlist_view"):
            if getattr(self.app, "screen", None) is self:
                self._deferred_playlist_update = True
            else:
                self.app._update_playlist_view()
        if hasattr(self.app, "_refresh_transport_controls"):
            if getattr(self.app, "screen", None) is self:
                self._deferred_playlist_update = True
            else:
                self.app._refresh_transport_controls()

    def _current_playing_path(self) -> Optional[Path]:
        playlist = getattr(self.app, "playlist", None)
        playing_index = getattr(self.app, "_playing_index", None)
        if (
            playlist
            and playing_index is not None
            and 0 <= playing_index < len(playlist.tracks)
        ):
            return playlist.tracks[playing_index].path
        return None

    def _reconcile_playing_index(self, playing_path: Optional[Path]) -> None:
        if playing_path is None:
            return
        playlist = getattr(self.app, "playlist", None)
        if not playlist:
            return
        for index, track in enumerate(playlist.tracks):
            if track.path == playing_path:
                setattr(self.app, "_playing_index", index)
                return
        setattr(self.app, "_playing_index", None)

    def _ensure_playlist(self) -> Playlist:
        playlist = getattr(self.app, "playlist", None)
        if playlist is None:
            playlist = Playlist([])
            setattr(self.app, "playlist", playlist)
        return playlist

    def _add_paths_to_playlist(self, paths: list[Path]) -> None:
        playlist = self._ensure_playlist()
        existing = {self._resolve_path(track.path) for track in playlist.tracks}
        new_paths = []
        for path in paths:
            resolved = self._resolve_path(path)
            if resolved in existing:
                continue
            existing.add(resolved)
            new_paths.append(path)
        if not new_paths:
            return
        added_tracks = [build_track_from_path(path) for path in new_paths]
        playlist.tracks.extend(added_tracks)
        if playlist.index < 0:
            playlist.index = 0
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()

    def _start_add_scan(
        self, paths: list[Path], *, allow_hidden_roots: list[Path] | None = None
    ) -> None:
        if not paths:
            return
        self._pending_commit_scan_id = None
        if self._active_scan_id is not None:
            self._cancel_active_scan()
        self._scan_id_counter += 1
        scan_id = self._scan_id_counter
        ctx = self._get_process_context()
        queue_handle: MPQueue = ctx.Queue()
        process: BaseProcess = ctx.Process(
            target=self._get_scan_worker_entrypoint(),
            args=(
                [str(path) for path in paths],
                [str(path) for path in allow_hidden_roots]
                if allow_hidden_roots
                else [],
                queue_handle,
            ),
            daemon=True,
        )
        reader_thread = threading.Thread(
            target=self._scan_queue_reader,
            args=(scan_id, process, queue_handle),
            daemon=True,
        )
        self._scan_states[scan_id] = _ScanState(
            scan_id=scan_id,
            process=process,
            queue=queue_handle,
            reader_thread=reader_thread,
        )
        self._active_scan_id = scan_id
        self._scan_progress = _ScanProgress()
        self._refresh_scan_controls()
        self._set_scan_status_visible(True)
        self._start_scan_spinner()
        self._update_scan_status()
        process.start()
        reader_thread.start()

    def _cancel_active_scan(self) -> None:
        active = self._active_scan_id
        if active is None:
            return
        state = self._scan_states.get(active)
        if not state or state.cancel_requested:
            return
        state.cancel_requested = True
        try:
            state.process.terminate()
        except Exception:
            pass
        self._refresh_scan_controls()

    def _scan_queue_reader(
        self, scan_id: int, process: BaseProcess, queue_handle: MPQueue
    ) -> None:
        while True:
            try:
                message = queue_handle.get(timeout=0.2)
            except queue.Empty:
                if not process.is_alive():
                    break
                continue
            if not isinstance(message, tuple) or not message:
                continue
            status = str(message[0])
            payload = message[1] if len(message) > 1 else None
            if status == "progress" and isinstance(payload, dict):
                try:
                    self.app.call_from_thread(
                        self._handle_scan_progress, scan_id, payload
                    )
                except Exception:
                    return
                continue
            try:
                self.app.call_from_thread(
                    self._handle_scan_result, scan_id, status, payload
                )
            except Exception:
                return
            return
        try:
            process.join(timeout=0)
        except Exception:
            pass
        state = self._scan_states.get(scan_id)
        if not state:
            return
        status = "canceled" if state.cancel_requested else "error"
        payload = None if status == "canceled" else "Scan process ended unexpectedly."
        try:
            self.app.call_from_thread(
                self._handle_scan_result, scan_id, status, payload
            )
        except Exception:
            return

    def _handle_scan_result(
        self,
        scan_id: int,
        status: str,
        payload: list[str] | str | None,
    ) -> None:
        state = self._scan_states.pop(scan_id, None)
        if not state:
            return
        was_active = self._active_scan_id == scan_id
        if was_active:
            self._active_scan_id = None
            self._refresh_scan_controls()
            self._set_scan_status_visible(False)
            self._stop_scan_spinner()
        if status != "ok":
            if status == "error" and hasattr(self.app, "_set_message"):
                self.app._set_message(str(payload))
            return
        if state.cancel_requested:
            return
        if not was_active:
            return
        if not isinstance(payload, list):
            return
        paths = [Path(item) for item in payload]
        if not paths:
            return
        self._start_commit_tracks(scan_id, payload)

    def _start_commit_tracks(self, scan_id: int, payload: list[str]) -> None:
        playlist_snapshot = list(self._ensure_playlist().tracks)
        self._pending_commit_scan_id = scan_id

        def worker() -> None:
            existing = {self._resolve_path(track.path) for track in playlist_snapshot}
            new_paths: list[Path] = []
            for item in payload:
                path = Path(item)
                resolved = self._resolve_path(path)
                if resolved in existing:
                    continue
                existing.add(resolved)
                new_paths.append(path)
            tracks = [build_track_from_path(path) for path in new_paths]
            try:
                self.app.call_from_thread(
                    self._finalize_commit_tracks, scan_id, tracks
                )
            except Exception:
                return

        threading.Thread(target=worker, daemon=True).start()

    def _finalize_commit_tracks(self, scan_id: int, tracks: list[Track]) -> None:
        if scan_id != self._pending_commit_scan_id:
            return
        self._pending_commit_scan_id = None
        if not tracks:
            return
        playlist = self._ensure_playlist()
        playlist.tracks.extend(tracks)
        if playlist.index < 0:
            playlist.index = 0
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()

    def _start_metadata_loader(self) -> None:
        if self._meta_timer:
            return

        def notify(path: Path, meta, generation: int) -> None:
            del generation
            try:
                self.app.call_from_thread(self._handle_metadata_loaded, path, meta)
            except Exception:
                return

        self._meta_loader.start(notify)
        self._meta_timer = self.set_interval(0.25, self._queue_visible_metadata)

    def _queue_visible_metadata(self) -> None:
        if not self._playlist_list:
            return
        playlist = self._ensure_playlist()
        if not playlist.tracks:
            return
        visible = self._playlist_list.get_visible_indices()
        if not visible:
            return
        prefetch = 2
        start = max(0, visible[0] - prefetch)
        end = min(len(playlist.tracks), visible[-1] + prefetch + 1)
        desired_paths: list[Path] = []
        for index in range(start, end):
            track = playlist.tracks[index]
            if get_cached_track_meta(track.path) is not None:
                title = self._playlist_display_title(track)
                self._playlist_list.set_title_override(track.path, title)
            desired_paths.append(track.path)
        self._meta_loader.update_visible(desired_paths)

    def _handle_metadata_loaded(self, path: Path, meta) -> None:
        if not self._playlist_list:
            return
        if meta:
            title = format_display_title(path, meta)
            self._playlist_list.set_title_override(path, title)
        else:
            self._playlist_list.set_title_override(path, path.name)
        focused = self._focused_playlist_index()
        if focused is not None:
            track = self._ensure_playlist().tracks[focused]
            if track.path == path:
                self._update_playlist_details(focused)

    def _handle_scan_progress(self, scan_id: int, payload: dict[str, object]) -> None:
        if scan_id != self._active_scan_id:
            return
        try:
            dirs_value = payload.get("dirs", 0)
            files_value = payload.get("files", 0)
            found_value = payload.get("found", 0)
            dirs = int(dirs_value) if isinstance(dirs_value, (int, str)) else 0
            files = int(files_value) if isinstance(files_value, (int, str)) else 0
            found = int(found_value) if isinstance(found_value, (int, str)) else 0
            path = str(payload.get("path", ""))
        except Exception:
            return
        self._scan_progress = _ScanProgress(
            dirs=dirs,
            files=files,
            found=found,
            path=path,
        )
        self._update_scan_status()

    def _refresh_scan_controls(self) -> None:
        try:
            cancel_button = self.query_one("#builder_files_cancel", Button)
        except Exception:
            return
        active = self._active_scan_id
        if active is None:
            cancel_button.disabled = True
            cancel_button.label = "Cancel"
            return
        state = self._scan_states.get(active)
        cancel_button.disabled = False
        cancel_button.label = (
            "Canceling..." if state and state.cancel_requested else "Cancel"
        )

    def _start_scan_spinner(self) -> None:
        if self._scan_spinner_timer is not None:
            return
        self._scan_spinner_timer = self.set_interval(0.1, self._advance_scan_spinner)

    def _stop_scan_spinner(self) -> None:
        if self._scan_spinner_timer is None:
            return
        try:
            self._scan_spinner_timer.stop()
        except Exception:
            pass
        self._scan_spinner_timer = None

    def _advance_scan_spinner(self) -> None:
        if self._active_scan_id is None:
            return
        self._scan_spinner_index = (self._scan_spinner_index + 1) % len(
            self._scan_spinner_frames
        )
        self._update_scan_status()

    def _update_scan_status(self) -> None:
        try:
            status = self.query_one("#builder_scan_status", Static)
        except Exception:
            return
        if self._active_scan_id is None or self._scan_progress is None:
            self._scan_status_text = ""
            status.update("")
            return
        spinner = self._scan_spinner_frames[self._scan_spinner_index]
        progress = self._scan_progress
        state = self._scan_states.get(self._active_scan_id)
        label = "Canceling..." if state and state.cancel_requested else "Scanning..."
        text = (
            f"{spinner} {label} "
            f"Found: {progress.found} | "
            f"Scanned: {progress.files} files / {progress.dirs} dirs | "
            f"Current: {progress.path} | Esc/Cancel to stop"
        )
        self._scan_status_text = text
        status.update(Text(text, overflow="ellipsis", no_wrap=True))

    def _set_scan_status_visible(self, visible: bool) -> None:
        try:
            status = self.query_one("#builder_scan_status", Static)
        except Exception:
            return
        status.display = visible
        if not visible:
            self._scan_status_text = ""
            status.update("")

    def _get_process_context(self) -> SpawnContext:
        return multiprocessing.get_context("spawn")

    def _get_scan_worker_entrypoint(
        self,
    ) -> Callable[[list[str], list[str], MPQueue], None]:
        return run_collect_audio_files

    def _confirm_hidden_add(self, paths: list[Path]) -> None:
        if not paths:
            return
        selection = paths[0]
        if not hasattr(self.app, "push_screen"):
            return
        self.app.push_screen(
            HiddenPathConfirm(selection),
            callback=lambda result: self._handle_hidden_confirm(result, paths),
        )

    def _handle_hidden_confirm(self, result: bool | None, paths: list[Path]) -> None:
        if result:
            self._start_add_scan(paths, allow_hidden_roots=paths)

    def on_unmount(self) -> None:
        if self._meta_timer:
            try:
                self._meta_timer.stop()
            except Exception:
                pass
            self._meta_timer = None
        self._meta_loader.stop()
        for scan_id in list(self._scan_states.keys()):
            state = self._scan_states.pop(scan_id, None)
            if not state:
                continue
            try:
                state.process.terminate()
            except Exception:
                pass
        self._active_scan_id = None
        self._refresh_scan_controls()
        self._set_scan_status_visible(False)
        self._stop_scan_spinner()
        if self._deferred_playlist_update:
            self._deferred_playlist_update = False
            if hasattr(self.app, "_update_playlist_view"):
                self.app._update_playlist_view()
            if hasattr(self.app, "_refresh_transport_controls"):
                self.app._refresh_transport_controls()

    def on_virtual_playlist_list_cursor_moved(
        self, message: VirtualPlaylistList.CursorMoved
    ) -> None:
        self._update_playlist_details(message.index)

    def on_virtual_playlist_list_scroll_changed(
        self, message: VirtualPlaylistList.ScrollChanged
    ) -> None:
        if not self._playlist_scrollbar:
            return
        self._playlist_scrollbar.set_state(
            total=message.total,
            offset=message.offset,
            viewport=message.viewport,
        )

    def on_virtual_playlist_scrollbar_scroll_requested(
        self, message: VirtualPlaylistScrollbar.ScrollRequested
    ) -> None:
        if not self._playlist_list:
            return
        self._playlist_list.set_scroll_offset(message.offset)

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return path.absolute()


def _panel_wrapper(title: str, child: Widget, *, panel_id: str) -> Container:
    panel = Container(child, id=panel_id)
    panel.border_title = title
    return panel


class HiddenPathConfirm(ModalScreen[bool]):
    """Confirm scan of an explicitly selected hidden/system path."""

    def __init__(self, path: Path) -> None:
        super().__init__()
        self._path = path

    def compose(self) -> ComposeResult:
        message = (
            "This location is hidden or system and is normally skipped during scans.\n"
            "It will be scanned because you selected it directly."
        )
        with Container(id="playlist_prompt"):
            yield Static("Hidden/System Path", id="prompt_title")
            yield Static(message, id="prompt_hint")
            yield Static(str(self._path), id="hidden_path_value")
            with Horizontal(id="prompt_buttons"):
                yield Button("Continue", id="hidden_path_continue")
                yield Button("Cancel", id="hidden_path_cancel")

    def on_mount(self) -> None:
        self.query_one("#hidden_path_continue", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "hidden_path_continue":
            self.dismiss(True)
            return
        self.dismiss(False)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self.dismiss(False)
            event.stop()
            return
        if event.key == "enter":
            focused = self.app.focused
            if isinstance(focused, Button):
                focused.press()
                event.stop()
