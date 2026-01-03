"""Playlist builder screen for RhythmSlicer."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import multiprocessing
from multiprocessing.context import SpawnContext
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue as MPQueue
from pathlib import Path
import queue
import threading
from typing import Callable, Optional, Sequence

import logging

from rich.text import Text
from textual import events
from textual.css.query import NoMatches
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Button, Static

from rhythm_slicer.metadata import TrackMeta
from rhythm_slicer.playlist_builder import (
    is_hidden_or_system,
    run_collect_audio_files,
)
from rhythm_slicer.playlist_io import save_m3u8
from rhythm_slicer.ui.file_browser import FileBrowserWidget
from rhythm_slicer.ui.marquee import Marquee
from rhythm_slicer.ui.metadata_loader import MetadataLoader, TrackRef
from rhythm_slicer.playlist_store_sqlite import (
    PlaylistStoreSQLite,
    PlaylistView,
    TrackRow,
)
from rhythm_slicer.ui.virtual_playlist_list import (
    VirtualPlaylistList,
    VirtualPlaylistScrollbar,
)

logger = logging.getLogger(__name__)


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


@dataclass
class _BulkRemoveProgress:
    total: int
    done: int = 0
    lock: threading.Lock = threading.Lock()

    def set(self, done: int, total: int) -> None:
        with self.lock:
            self.done = done
            self.total = total

    def get(self) -> tuple[int, int]:
        with self.lock:
            return self.done, self.total


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
        self._remove_cancel_event: threading.Event | None = None
        self._remove_modal: RemoveTracksProgress | None = None
        self._pending_commit_scan_id: int | None = None
        self._deferred_playlist_update = False
        self._playlist_store: PlaylistStoreSQLite | None = None
        self._playlist_view = PlaylistView(playlist_id="main")
        self._playlist_count = 0
        self._playlist_request_id = 0
        self._playlist_view_generation = 0
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
        self._playlist_list = self.query_one("#builder_playlist", VirtualPlaylistList)
        self._playlist_scrollbar = self.query_one(
            "#builder_playlist_scrollbar", VirtualPlaylistScrollbar
        )
        store = getattr(self.app, "_playlist_store", None)
        if isinstance(store, PlaylistStoreSQLite):
            self._playlist_store = store
            playlist_id = getattr(self.app, "_playlist_id", "main")
            self._playlist_view = PlaylistView(playlist_id=playlist_id)
            self._meta_loader = MetadataLoader(
                max_workers=2,
                queue_limit=100,
                get_cached=store.fetch_metadata_if_valid,
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
            self._select_all_tracks()
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
        if not self._playlist_store:
            return
        self._playlist_view_generation += 1
        self._meta_generation += 1
        self._meta_loader.set_generation(self._meta_generation)
        if self._playlist_count == 0:
            try:
                total = self._playlist_store.count(self._playlist_view)
            except Exception:
                total = 0
            self._playlist_count = total
            self._playlist_list.set_total_count(total)
        self._request_playlist_page()

    def _request_playlist_page(self) -> None:
        if not self._playlist_list or not self._playlist_store:
            return
        store = self._playlist_store
        view = self._playlist_view
        offset, total, viewport = self._playlist_list.view_info()
        if viewport <= 0:
            return
        prefetch = 2
        start = max(0, offset - prefetch)
        max_total = max(total, self._playlist_count)
        end = offset + viewport + prefetch
        if max_total:
            end = min(max_total, end)
        if end <= start and max_total:
            return
        self._playlist_request_id += 1
        request_id = self._playlist_request_id
        generation = self._playlist_view_generation

        def worker() -> None:
            total_count = store.count(view)
            rows = store.page(view, start, end - start)
            try:
                self.app.call_from_thread(
                    self._apply_playlist_page,
                    request_id,
                    generation,
                    start,
                    total_count,
                    rows,
                )
            except Exception:
                return

        self.app.run_worker(worker, exclusive=False, thread=True)

    def _apply_playlist_page(
        self,
        request_id: int,
        generation: int,
        offset: int,
        total_count: int,
        rows: Sequence[TrackRow],
    ) -> None:
        if generation != self._playlist_view_generation:
            return
        if request_id != self._playlist_request_id:
            return
        self._playlist_count = total_count
        if not self._playlist_list:
            return
        if total_count <= 0:
            self._playlist_list.set_tracks([])
            self._playlist_list.set_total_count(0)
            self._clear_playlist_details()
            return
        self._playlist_list.set_total_count(total_count)
        self._playlist_list.set_rows(offset, rows)
        self._queue_metadata_for_rows(rows)
        focused = self._focused_playlist_index()
        if focused is not None:
            self._update_playlist_details(focused)

    def _playlist_display_title(self, row: TrackRow | None) -> str:
        if not row:
            return ""
        title = row.title or row.path.name
        if row.artist:
            return f"{row.artist} - {title}"
        return title

    def _playlist_details_text(self, row: TrackRow | None) -> str:
        if not row:
            return ""
        title = self._playlist_display_title(row)
        return f"{title} ({row.path})"

    def _clear_playlist_details(self) -> None:
        try:
            self.query_one("#builder_playlist_details", Marquee).set_text("")
        except NoMatches:
            return

    def _update_playlist_details(self, index: Optional[int]) -> None:
        if not self._playlist_list or not self._playlist_store:
            return
        if index is None or index < 0:
            self._clear_playlist_details()
            return
        row = self._playlist_list.get_cached_row(index)
        if row is None:
            row = self._playlist_store.get_row_at(self._playlist_view, index)
        if row is None:
            self._clear_playlist_details()
            return
        details = self._playlist_details_text(row)
        try:
            self.query_one("#builder_playlist_details", Marquee).set_text(details)
        except NoMatches:
            return

    def _focused_playlist_index(self) -> Optional[int]:
        if not self._playlist_list:
            return None
        if not self._playlist_list:
            return None
        return self._playlist_list.cursor_index

    def _toggle_playlist_selection(self) -> None:
        if self._playlist_list:
            self._playlist_list.toggle_checked_at_cursor()

    def _select_all_tracks(self) -> None:
        if not self._playlist_store or not self._playlist_list:
            return
        store = self._playlist_store
        playlist_list = self._playlist_list
        playlist_id = self._playlist_view.playlist_id

        async def worker() -> None:
            track_ids = await asyncio.to_thread(
                store.list_track_ids,
                playlist_id,
            )
            playlist_list.set_checked_track_ids(track_ids)

        self.app.run_worker(worker(), exclusive=True)

    def _remove_selected_tracks(self) -> None:
        if not self._playlist_store:
            return
        store = self._playlist_store
        view = self._playlist_view
        playlist_id = self._playlist_view.playlist_id
        selected_track_ids = (
            set(self._playlist_list.get_checked_track_ids())
            if self._playlist_list
            else set()
        )
        focused_index = self._focused_playlist_index()
        if not selected_track_ids and focused_index is None:
            return
        selection = set(selected_track_ids)
        if not selection and focused_index is not None:
            row = store.get_row_at(view, focused_index)
            if row:
                selection = {row.track_id}
        if not selection:
            if hasattr(self.app, "_set_message"):
                self.app._set_message("No tracks selected", level="warn")
            logger.info("Remove requested with no selection")
            return
        cursor_index = focused_index or 0
        playing_track_id = self._current_playing_track_id()
        original_count = self._playlist_count
        cancel_event = threading.Event()
        self._remove_cancel_event = cancel_event
        total_selection = len(selection)
        progress_state = _BulkRemoveProgress(total_selection)
        self._remove_modal = RemoveTracksProgress(
            total_selection,
            cancel_event,
            progress=progress_state,
        )
        if hasattr(self.app, "push_screen"):
            self.app.push_screen(self._remove_modal)
        logger.info(
            "Bulk remove requested count=%d playing_track_id=%s",
            total_selection,
            playing_track_id,
        )

        selected_ids = sorted(selection)
        selected_set = set(selected_ids)

        async def worker() -> None:
            def apply() -> tuple[set[int], int, int]:
                logger.info("Bulk remove worker start selection=%d", len(selected_ids))
                def report(done: int, total: int) -> None:
                    progress_state.set(done, total)

                removed = store.remove_tracks_bulk(
                    playlist_id,
                    selected_ids,
                    cancel=cancel_event,
                    progress=report,
                )
                total = store.count(view)
                logger.info(
                    "Bulk remove worker done removed=%d total=%d", removed, total
                )
                return selected_set, removed, total

            try:
                selection, removed, total = await asyncio.to_thread(apply)
            except Exception:
                logger.exception("Bulk remove failed")
                self.app.call_later(self._finalize_remove_modal)
                return
            self.app.call_later(self._finalize_remove_modal)
            if cancel_event.is_set() or removed <= 0:
                logger.info(
                    "Bulk remove canceled or removed=0 canceled=%s",
                    cancel_event.is_set(),
                )
                return
            if not selection:
                return
            self._handle_remove_complete(
                selection,
                playing_track_id,
                original_count,
                total,
                cursor_index,
            )
            logger.info("Bulk remove complete removed=%d total=%d", removed, total)

        self.app.run_worker(worker(), exclusive=True)
        return

    def _finalize_remove_modal(self) -> None:
        if self._remove_modal:
            try:
                self._remove_modal.dismiss(None)
            except Exception:
                logger.exception("Failed to dismiss remove modal")
                pass
        self._remove_modal = None
        self._remove_cancel_event = None

    def action_remove_from_playlist(self) -> None:
        self._remove_selected_tracks()

    def _selected_or_focused_track_ids(self) -> set[int]:
        if self._playlist_list:
            checked = self._playlist_list.get_checked_track_ids()
            if checked:
                return set(checked)
        focused = self._focused_playlist_index()
        if focused is None:
            return set()
        row = (
            self._playlist_list.get_cached_row(focused) if self._playlist_list else None
        )
        if row is None:
            return set()
        return {row.track_id}

    def _current_playing_track_id(self) -> Optional[int]:
        return getattr(self.app, "_playing_track_id", None)

    def _handle_remove_complete(
        self,
        removed_track_ids: set[int],
        playing_track_id: Optional[int],
        original_count: int,
        total: int,
        cursor_index: int,
    ) -> None:
        if self._playlist_list:
            self._playlist_list.clear_checked()
        if playing_track_id in removed_track_ids:
            if total <= 0:
                self._stop_playback_for_empty_playlist()
            else:
                setattr(self.app, "_playing_track_id", None)
                setattr(self.app, "_playing_index", None)
        self._playlist_count = total
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()
        self._restore_playlist_cursor(cursor_index)

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
        setattr(self.app, "_playing_track_id", None)

    def _restore_playlist_cursor(self, preferred_index: int) -> None:
        if not self._playlist_list:
            return
        if self._playlist_count <= 0:
            return
        self._playlist_list.set_cursor_index(preferred_index)
        self._update_playlist_details(self._focused_playlist_index())

    def _move_selected_tracks(self, direction: str) -> None:
        if not self._playlist_store:
            return
        store = self._playlist_store
        view = self._playlist_view
        playlist_id = self._playlist_view.playlist_id
        selection = (
            set(self._playlist_list.get_checked_track_ids())
            if self._playlist_list
            else set()
        )
        focused = self._focused_playlist_index()
        if not selection and focused is None:
            return

        async def worker() -> None:
            def apply() -> int:
                selected_ids = set(selection)
                if not selected_ids and focused is not None:
                    row = store.get_row_at(view, focused)
                    if row:
                        selected_ids = {row.track_id}
                if not selected_ids:
                    return store.count(view)
                store.move_tracks(
                    playlist_id,
                    selected_ids,
                    "up" if direction == "up" else "down",
                )
                return store.count(view)

            total = await asyncio.to_thread(apply)
            self._handle_reorder_complete(total)

        self.app.run_worker(worker(), exclusive=True)

    def _save_playlist(self, *, force_prompt: bool) -> None:
        if not self._playlist_store or self._playlist_count <= 0:
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
            paths = self._playlist_store.list_paths(self._playlist_view.playlist_id)
            save_m3u8(paths, dest, mode="auto")
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

    def _handle_reorder_complete(self, total: int) -> None:
        self._playlist_count = total
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
                if process.is_alive():
                    continue
                if getattr(process, "exitcode", None) is None:
                    continue
                break
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
        if not self._playlist_store:
            return
        store = self._playlist_store
        view = self._playlist_view
        playlist_id = self._playlist_view.playlist_id
        self._pending_commit_scan_id = scan_id

        def worker() -> None:
            new_paths: list[Path] = [Path(item) for item in payload]
            try:
                store.add_paths(playlist_id, new_paths)
                total = store.count(view)
                self.app.call_from_thread(self._finalize_commit_tracks, scan_id, total)
            except Exception:
                return

        threading.Thread(target=worker, daemon=True).start()

    def _finalize_commit_tracks(self, scan_id: int, total: int) -> None:
        if scan_id != self._pending_commit_scan_id:
            return
        self._pending_commit_scan_id = None
        self._playlist_count = total
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()

    def _start_metadata_loader(self) -> None:
        if self._meta_timer:
            return

        def notify(track_id: int, path: Path, meta, generation: int) -> None:
            try:
                self.app.call_from_thread(
                    self._handle_metadata_loaded, track_id, path, meta, generation
                )
            except Exception:
                return

        self._meta_loader.start(notify)
        self._meta_timer = None

    def _queue_metadata_for_rows(self, rows: Sequence[TrackRow]) -> None:
        if not rows:
            return
        refs = [TrackRef(row.track_id, row.path) for row in rows]
        self._meta_loader.update_visible(refs)

    def _handle_metadata_loaded(
        self,
        track_id: int,
        path: Path,
        meta,
        generation: int,
    ) -> None:
        if generation != self._meta_generation:
            return
        if not self._playlist_store or not self._playlist_list:
            return
        if meta is None:
            meta = TrackMeta(artist=None, title=None, album=None, duration_seconds=None)
        try:
            self._playlist_store.upsert_metadata(track_id, meta)
        except Exception:
            return
        row = self._playlist_store.get_row_by_track_id(track_id)
        if row:
            self._playlist_list.update_row(track_id, row)
        focused = self._focused_playlist_index()
        if focused is not None:
            cached = self._playlist_list.get_cached_row(focused)
            if cached and cached.track_id == track_id:
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
            self.call_later(self._start_add_scan, paths, allow_hidden_roots=paths)

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
        self._request_playlist_page()

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


class RemoveTracksProgress(ModalScreen[None]):
    """Modal progress overlay for bulk removal."""

    def __init__(
        self,
        total: int,
        cancel_event: threading.Event,
        *,
        progress: _BulkRemoveProgress | None = None,
    ) -> None:
        super().__init__()
        self._total = max(0, total)
        self._done = 0
        self._cancel_event = cancel_event
        self._progress = progress
        self._spinner_index = 0
        self._spinner_timer: Timer | None = None
        self._spinner_frames = ["|", "/", "-", "\\"]

    def compose(self) -> ComposeResult:
        with Container(id="builder_remove_overlay"):
            yield Static("Removing Tracks", id="builder_remove_title")
            yield Static("", id="builder_remove_status")
            with Horizontal(id="builder_remove_buttons"):
                yield Button("Cancel", id="builder_remove_cancel")

    def on_mount(self) -> None:
        self._spinner_timer = self.set_interval(0.1, self._advance_spinner)
        self._refresh_status()
        try:
            self.query_one("#builder_remove_cancel", Button).focus()
        except Exception:
            return

    def on_unmount(self) -> None:
        if self._spinner_timer is None:
            return
        try:
            self._spinner_timer.stop()
        except Exception:
            pass
        self._spinner_timer = None

    def update_progress(self, done: int, total: int | None = None) -> None:
        self._done = max(0, done)
        if total is not None:
            self._total = max(0, total)
        self._refresh_status()

    def _advance_spinner(self) -> None:
        self._spinner_index = (self._spinner_index + 1) % len(self._spinner_frames)
        self._refresh_status()

    def _refresh_status(self) -> None:
        try:
            status = self.query_one("#builder_remove_status", Static)
        except Exception:
            return
        if self._progress is not None:
            done, total = self._progress.get()
            self._done = done
            self._total = total
        spinner = self._spinner_frames[self._spinner_index]
        total = self._total
        if self._cancel_event.is_set():
            status.update(f"{spinner} Canceling...")
            return
        if total > 0:
            status.update(f"{spinner} Removing {min(self._done, total)} / {total}")
        else:
            status.update(f"{spinner} Removing...")

    def _cancel(self) -> None:
        if not self._cancel_event.is_set():
            self._cancel_event.set()
            logger.info("Bulk remove cancel requested")
        try:
            button = self.query_one("#builder_remove_cancel", Button)
        except Exception:
            button = None
        if button:
            button.disabled = True
            button.label = "Canceling..."
        self._refresh_status()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "builder_remove_cancel":
            self._cancel()
            return
        self.dismiss(None)

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape":
            self._cancel()
            event.stop()
