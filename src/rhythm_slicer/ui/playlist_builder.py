"""Playlist builder screen for RhythmSlicer."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from rhythm_slicer.metadata import get_track_meta
from rhythm_slicer.playlist import Playlist, Track
from rhythm_slicer.playlist_builder import (
    build_track_from_path,
    collect_audio_files,
    reorder_items,
)
from rhythm_slicer.playlist_io import save_m3u8
from rhythm_slicer.ui.file_browser import FileBrowserWidget
from rhythm_slicer.ui.marquee import Marquee


class PlaylistBuilderScreen(Screen):
    """Two-pane playlist builder inspired by Midnight Commander."""

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._start_path = start_path
        self._file_browser: Optional[FileBrowserWidget] = None
        self._playlist_table: Optional[DataTable] = None
        self._playlist_selection: set[int] = set()

    def compose(self) -> ComposeResult:
        with Container(id="builder_root"):
            with Horizontal(id="builder_panes"):
                yield _panel_wrapper(
                    "Files",
                    Vertical(
                        FileBrowserWidget(self._start_path, id="builder_file_browser"),
                        Horizontal(
                            Button("Add", id="builder_files_add"),
                            id="builder_files_actions",
                        ),
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
                        DataTable(id="builder_playlist"),
                        Horizontal(
                            Button(
                                "Select All",
                                id="builder_playlist_select_all",
                            ),
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
        self._playlist_table = self.query_one("#builder_playlist", DataTable)
        self._init_playlist_table()
        self._refresh_playlist_entries()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "builder_files_add":
            if not self._file_browser:
                return
            selected = self._file_browser.selected_path
            if selected:
                self._add_paths_to_playlist([selected])
            return
        if button_id == "builder_playlist_select_all":
            playlist = self._ensure_playlist()
            self._playlist_selection = set(range(len(playlist.tracks)))
            self._refresh_playlist_entries()
            return
        if button_id == "builder_playlist_clear":
            self._playlist_selection.clear()
            self._refresh_playlist_entries()
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
        if key in {"pageup", "pagedown"}:
            event.stop()
            return
        if key == "escape":
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
            self._remove_selected_tracks()
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
        if focused is self._playlist_table:
            return True
        playlist_ids = {
            "builder_playlist_save",
            "builder_playlist_load",
            "builder_done",
            "builder_playlist_select_all",
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

    def _init_playlist_table(self) -> None:
        if not self._playlist_table:
            return
        self._playlist_table.clear(columns=True)
        self._playlist_table.add_column("Track", key="track")
        self._playlist_table.show_header = False
        self._playlist_table.cursor_type = "row"
        self._playlist_table.show_cursor = True
        self._playlist_table.zebra_stripes = False
        self._playlist_table.show_horizontal_scrollbar = False

    def _refresh_playlist_entries(self) -> None:
        if not self._playlist_table:
            return
        playlist = self._ensure_playlist()
        current_row = self._playlist_table.cursor_row or 0
        self._playlist_table.clear()
        count_width = self._playlist_count_width()
        for index, track in enumerate(playlist.tracks):
            text = self._playlist_row_text(track, index, count_width)
            self._playlist_table.add_row(text, key=str(index))
        self._restore_cursor(self._playlist_table, current_row)
        if playlist.tracks:
            self._update_playlist_details(self._focused_playlist_index())
        else:
            self._clear_playlist_details()

    def _playlist_count_width(self) -> int:
        playlist = self._ensure_playlist()
        return max(2, len(str(len(playlist.tracks) or 1)))

    def _playlist_row_text(self, track: Track, index: int, count_width: int) -> Text:
        title = self._playlist_display_title(track)
        marker = "[x]" if index in self._playlist_selection else "[ ]"
        label = f"{marker} {index + 1:>{count_width}d} {title}"
        style = "#5fc9d6" if index in self._playlist_selection else "#c6d0f2"
        return Text(label, style=style, overflow="ellipsis", no_wrap=True)

    def _playlist_display_title(self, track: Track) -> str:
        meta = get_track_meta(track.path)
        if meta.title and meta.artist:
            return f"{meta.title} - {meta.artist}"
        if meta.title:
            return meta.title
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

    def _update_playlist_row(self, index: int) -> None:
        if not self._playlist_table:
            return
        playlist = self._ensure_playlist()
        if index < 0 or index >= len(playlist.tracks):
            return
        count_width = self._playlist_count_width()
        text = self._playlist_row_text(playlist.tracks[index], index, count_width)
        try:
            self._playlist_table.update_cell(
                str(index),
                "track",
                text,
                update_width=False,
            )
        except Exception:
            cursor_row = self._playlist_table.cursor_row
            scroll_y = self._playlist_table.scroll_y
            self._refresh_playlist_entries()
            if cursor_row is not None:
                self._playlist_table.move_cursor(row=cursor_row, column=0, scroll=False)
            self._playlist_table.scroll_to(y=scroll_y, animate=False, immediate=True)

    def _restore_cursor(self, table: DataTable, row: int) -> None:
        if table.row_count == 0:
            return
        target = max(0, min(row, table.row_count - 1))
        table.move_cursor(row=target, column=0, scroll=False)

    def _focused_playlist_index(self) -> Optional[int]:
        if not self._playlist_table:
            return None
        row = self._playlist_table.cursor_row
        if row is None or row < 0:
            return None
        return row

    def _toggle_playlist_selection(self) -> None:
        index = self._focused_playlist_index()
        if index is None:
            return
        if index in self._playlist_selection:
            self._playlist_selection.remove(index)
        else:
            self._playlist_selection.add(index)
        self._update_playlist_row(index)

    def _remove_selected_tracks(self) -> None:
        playlist = self._ensure_playlist()
        if playlist.is_empty():
            return
        if not self._playlist_selection:
            return
        tracks = getattr(playlist, "tracks", None)
        if not isinstance(tracks, list):
            raise RuntimeError(
                "PlaylistBuilderScreen expected playlist.tracks to be a list."
            )
        playing_path = self._current_playing_path()
        for index in sorted(self._playlist_selection, reverse=True):
            if 0 <= index < len(tracks):
                tracks.pop(index)
        self._playlist_selection.clear()
        self._reconcile_playing_index(playing_path)
        playlist.clamp_index()
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()

    def _move_selected_tracks(self, direction: str) -> None:
        playlist = self._ensure_playlist()
        if playlist.is_empty():
            return
        selection = self._playlist_selection
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
        self._playlist_selection = set(new_selection)
        self._reconcile_playing_index(playing_path)
        self._refresh_playlist_after_edit()
        self._refresh_playlist_entries()
        if self._playlist_table and new_selection:
            self._playlist_table.move_cursor(
                row=min(new_selection), column=0, scroll=False
            )

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
        self._playlist_selection.clear()
        self._refresh_playlist_entries()

    def _refresh_playlist_after_edit(self) -> None:
        if hasattr(self.app, "_reset_play_order"):
            self.app._reset_play_order()
        if hasattr(self.app, "_sync_play_order_pos"):
            self.app._sync_play_order_pos()
        if hasattr(self.app, "_update_playlist_view"):
            self.app._update_playlist_view()
        if hasattr(self.app, "_refresh_transport_controls"):
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
        for path in collect_audio_files(paths):
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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table is not self._playlist_table:
            return
        self.set_focus(self._playlist_table)
        event.stop()
        index = self._focused_playlist_index()
        if index is None:
            return
        if index in self._playlist_selection:
            self._playlist_selection.remove(index)
        else:
            self._playlist_selection.add(index)
        self._update_playlist_row(index)
        self._update_playlist_details(index)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table is not self._playlist_table:
            return
        self.set_focus(self._playlist_table)
        event.stop()
        self._update_playlist_details(event.cursor_row)

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.data_table is not self._playlist_table:
            return
        self.set_focus(self._playlist_table)
        event.stop()

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
