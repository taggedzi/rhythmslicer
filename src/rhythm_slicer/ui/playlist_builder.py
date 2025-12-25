"""Playlist builder screen for RhythmSlicer."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Select, Static

from rhythm_slicer.metadata import get_track_meta
from rhythm_slicer.playlist import Playlist, Track
from rhythm_slicer.playlist_builder import (
    BrowserEntry,
    FileBrowserModel,
    build_track_from_path,
    collect_audio_files,
    list_drives,
    reorder_items,
)
from rhythm_slicer.playlist_io import save_m3u8


class PlaylistBuilderScreen(Screen):
    """Two-pane playlist builder inspired by Midnight Commander."""

    BROWSER_HINTS = (
        "Up/Down PgUp/PgDn Home/End Move | Enter/Right Open | Left Up | "
        "Space Select | F5 Add | Ins Filter | Tab Switch | Esc Clear | b Back"
    )
    PLAYLIST_HINTS = (
        "Up/Down PgUp/PgDn Home/End Move | Space Select | d Delete | u/j Move | "
        "s Save | S Save As | l Load | Tab Switch | Esc Clear | b Back"
    )

    def __init__(self, start_path: Path) -> None:
        super().__init__()
        self._browser = FileBrowserModel(start_path)
        self._browser_entries: list[BrowserEntry] = []
        self._browser_table: Optional[DataTable] = None
        self._playlist_table: Optional[DataTable] = None
        self._playlist_selection: set[int] = set()
        self._focused_pane = "browser"
        self._filter_active = False
        self._filter_text = ""
        self._last_browser_click_time = 0.0
        self._last_browser_click_row: Optional[int] = None
        self._last_enter_nav_time = 0.0

    def compose(self) -> ComposeResult:
        with Container(id="builder_root"):
            with Horizontal(id="builder_panes"):
                yield _panel_wrapper(
                    "Files",
                    Vertical(
                        DataTable(id="builder_browser"),
                        Horizontal(
                            Button("Select All", id="builder_files_select_all"),
                            Button("Clear", id="builder_files_clear"),
                            id="builder_files_actions",
                        ),
                        id="builder_left_stack",
                    ),
                    panel_id="builder_left_panel",
                )
                yield _panel_wrapper(
                    "Playlist",
                    Vertical(
                        DataTable(id="builder_playlist"),
                        Horizontal(
                            Button(
                                "Select All",
                                id="builder_playlist_select_all",
                            ),
                            Button("Clear", id="builder_playlist_clear"),
                            Button("Save", id="builder_playlist_save"),
                            Button("Load", id="builder_playlist_load"),
                            id="builder_playlist_actions",
                        ),
                        id="builder_right_stack",
                    ),
                    panel_id="builder_right_panel",
                )
            yield Static("", id="builder_hints")

    def on_mount(self) -> None:
        self._browser_table = self.query_one("#builder_browser", DataTable)
        self._playlist_table = self.query_one("#builder_playlist", DataTable)
        self._init_browser_table()
        self._init_playlist_table()
        self._refresh_browser_entries()
        self._refresh_playlist_entries()
        self._update_hints()
        if self._browser_table:
            self.set_focus(self._browser_table)

    def on_focus(self, event: events.Focus) -> None:
        if event.widget is self._browser_table:
            self._focused_pane = "browser"
        elif event.widget is self._playlist_table:
            self._focused_pane = "playlist"
        elif isinstance(event.widget, Button):
            button_id = event.widget.id or ""
            if button_id in {"builder_files_select_all", "builder_files_clear"}:
                self._focused_pane = "browser"
            elif button_id in {
                "builder_playlist_select_all",
                "builder_playlist_clear",
                "builder_playlist_save",
                "builder_playlist_load",
            }:
                self._focused_pane = "playlist"
        self._update_hints()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "builder_files_select_all":
            self._browser.clear_selection()
            for entry in self._browser_entries:
                if entry.is_parent:
                    continue
                self._browser.toggle_selection(entry)
            self._refresh_browser_entries()
            return
        if button_id == "builder_files_clear":
            self._browser.clear_selection()
            self._refresh_browser_entries()
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
        if button_id == "builder_playlist_save":
            self._save_playlist(force_prompt=False)
            return
        if button_id == "builder_playlist_load":
            self._load_playlist()
            return

    def on_key(self, event: events.Key) -> None:
        key = event.key
        if key in {"pageup", "pagedown"}:
            event.stop()
            return
        try:
            focused = self.focused
        except Exception:
            focused = None
        is_table_focus = focused in {self._browser_table, self._playlist_table}
        if self._focused_pane == "browser" and self._filter_active:
            if key in {"escape"}:
                self._filter_active = False
                self._filter_text = ""
                self._refresh_browser_entries()
                event.stop()
                return
            if key in {"enter"}:
                self._filter_active = False
                self._update_hints()
                event.stop()
                return
            if key in {"backspace", "delete"}:
                if self._filter_text:
                    self._filter_text = self._filter_text[:-1]
                    self._refresh_browser_entries()
                event.stop()
                return
            char = event.character
            if char and len(char) == 1 and char.isprintable():
                self._filter_text += char
                self._refresh_browser_entries()
                event.stop()
                return
        if key == "b":
            self.app.pop_screen()
            event.stop()
            return
        if key == "escape":
            self._clear_selection()
            event.stop()
            return
        if not is_table_focus:
            return
        if self._focused_pane == "browser":
            if key == "insert":
                self._filter_active = True
                self._filter_text = ""
                self._refresh_browser_entries()
                event.stop()
                return
            if key in {"enter", "right"}:
                self._last_enter_nav_time = time.monotonic()
                self._enter_directory()
                event.stop()
                return
            if key == "left":
                self._go_up()
                event.stop()
                return
            if key == "space":
                self._toggle_browser_selection()
                event.stop()
                return
            if key == "f5":
                self._add_selection_to_playlist()
                event.stop()
                return
        else:
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

    def _init_browser_table(self) -> None:
        if not self._browser_table:
            return
        self._browser_table.clear(columns=True)
        self._browser_table.add_column("Entry", key="entry")
        self._browser_table.show_header = False
        self._browser_table.cursor_type = "row"
        self._browser_table.show_cursor = True
        self._browser_table.zebra_stripes = False

    def _init_playlist_table(self) -> None:
        if not self._playlist_table:
            return
        self._playlist_table.clear(columns=True)
        self._playlist_table.add_column("Track", key="track")
        self._playlist_table.show_header = False
        self._playlist_table.cursor_type = "row"
        self._playlist_table.show_cursor = True
        self._playlist_table.zebra_stripes = False

    def _toggle_focus(self) -> None:
        if self._focused_pane == "browser" and self._playlist_table:
            self._focused_pane = "playlist"
            self.set_focus(self._playlist_table)
            return
        if self._browser_table:
            self._focused_pane = "browser"
            self.set_focus(self._browser_table)

    def _update_hints(self) -> None:
        if self._focused_pane == "browser" and self._filter_active:
            hint = f"Filter: {self._filter_text or '...'}"
        else:
            hint = (
                self.BROWSER_HINTS
                if self._focused_pane == "browser"
                else self.PLAYLIST_HINTS
            )
        hint_widget = self.query_one("#builder_hints", Static)
        hint_widget.update(hint)

    def _refresh_browser_entries(self) -> None:
        if not self._browser_table:
            return
        current_row = self._browser_table.cursor_row or 0
        entries = self._browser.list_entries()
        if self._filter_text:
            filtered = [entries[0]]
            filtered.extend(
                entry
                for entry in entries[1:]
                if self._entry_matches_filter(entry, self._filter_text)
            )
            self._browser_entries = filtered
        else:
            self._browser_entries = entries
        self._browser_table.clear()
        for entry in self._browser_entries:
            text = self._browser_row_text(entry)
            self._browser_table.add_row(text, key=str(entry.path))
        self._restore_cursor(self._browser_table, current_row)
        self._update_browser_title()
        self._update_hints()

    def _browser_row_text(self, entry: BrowserEntry) -> Text:
        if entry.is_parent:
            return Text("   ..", style="#8a93a3")
        selected = self._browser.is_selected(entry.path)
        marker = "[x]" if selected else "[ ]"
        label = f"{marker} {entry.name}{'/' if entry.is_dir else ''}"
        style = "#5fc9d6" if entry.is_dir else "#c6d0f2"
        return Text(label, style=style)

    def _update_browser_title(self) -> None:
        panel = self.query_one("#builder_left_panel", Container)
        title = f"Files: {self._browser.current_path}"
        if self._filter_text:
            title = f"{title} | Filter: {self._filter_text}"
        panel.border_title = title

    def _refresh_playlist_entries(self) -> None:
        if not self._playlist_table:
            return
        playlist = self._ensure_playlist()
        current_row = self._playlist_table.cursor_row or 0
        self._playlist_table.clear()
        count_width = max(2, len(str(len(playlist.tracks) or 1)))
        for index, track in enumerate(playlist.tracks):
            text = self._playlist_row_text(track, index, count_width)
            self._playlist_table.add_row(text, key=str(index))
        self._restore_cursor(self._playlist_table, current_row)

    def _playlist_row_text(self, track: Track, index: int, count_width: int) -> Text:
        meta = get_track_meta(track.path)
        if meta.title and meta.artist:
            title = f"{meta.title} - {meta.artist}"
        elif meta.title:
            title = meta.title
        else:
            title = track.path.name
        marker = "[x]" if index in self._playlist_selection else "[ ]"
        label = f"{marker} {index + 1:>{count_width}d} {title}"
        style = "#5fc9d6" if index in self._playlist_selection else "#c6d0f2"
        return Text(label, style=style)

    def _restore_cursor(self, table: DataTable, row: int) -> None:
        if table.row_count == 0:
            return
        target = max(0, min(row, table.row_count - 1))
        table.move_cursor(row=target, column=0, scroll=False)

    def _focused_browser_entry(self) -> Optional[BrowserEntry]:
        if not self._browser_table:
            return None
        row = self._browser_table.cursor_row
        if row is None or row < 0 or row >= len(self._browser_entries):
            return None
        return self._browser_entries[row]

    def _focused_playlist_index(self) -> Optional[int]:
        if not self._playlist_table:
            return None
        row = self._playlist_table.cursor_row
        if row is None or row < 0:
            return None
        return row

    def _enter_directory(self) -> None:
        entry = self._focused_browser_entry()
        if entry is None:
            return
        if entry.is_parent:
            if self._browser.is_at_root():
                self.app.run_worker(self._drive_picker_flow(), exclusive=True)
                return
            self._browser.change_directory(entry.path)
        elif entry.is_dir:
            self._browser.change_directory(entry.path)
        self._refresh_browser_entries()

    def _go_up(self) -> None:
        if self._browser.is_at_root():
            self.app.run_worker(self._drive_picker_flow(), exclusive=True)
            return
        if self._browser.go_up():
            self._refresh_browser_entries()

    def _toggle_browser_selection(self) -> None:
        entry = self._focused_browser_entry()
        if entry is None:
            return
        if entry.is_parent:
            return
        self._browser.toggle_selection(entry)
        self._refresh_browser_entries()

    def _add_selection_to_playlist(self) -> None:
        selected = self._browser.selected_paths()
        if not selected:
            return
        self._add_paths_to_playlist(selected)

    def _toggle_playlist_selection(self) -> None:
        index = self._focused_playlist_index()
        if index is None:
            return
        if index in self._playlist_selection:
            self._playlist_selection.remove(index)
        else:
            self._playlist_selection.add(index)
        self._refresh_playlist_entries()

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

    def _clear_selection(self) -> None:
        if self._focused_pane == "browser":
            self._browser.clear_selection()
            self._refresh_browser_entries()
            return
        self._playlist_selection.clear()
        self._refresh_playlist_entries()

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
        await self.app._load_playlist_flow()
        self._playlist_selection.clear()
        self._refresh_playlist_entries()

    async def _drive_picker_flow(self) -> None:
        drives = list_drives()
        if not drives:
            if hasattr(self.app, "_set_message"):
                self.app._set_message("No drives detected", level="warn")
            return
        result = await self.app.push_screen_wait(DrivePrompt(drives))
        if not result:
            return
        self._browser.change_directory(result)
        self._refresh_browser_entries()

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
                self.app._playing_index = index
                return
        self.app._playing_index = None

    def _ensure_playlist(self) -> Playlist:
        if getattr(self.app, "playlist", None) is None:
            self.app.playlist = Playlist([])
        return self.app.playlist

    def _entry_matches_filter(self, entry: BrowserEntry, needle: str) -> bool:
        if entry.is_parent:
            return True
        lowered = needle.casefold()
        if lowered in entry.name.casefold():
            return True
        if entry.is_dir:
            return False
        meta = get_track_meta(entry.path)
        title = meta.title or ""
        artist = meta.artist or ""
        combined = f"{title} {artist}".casefold()
        return lowered in combined

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
        if event.data_table is self._browser_table:
            self._focused_pane = "browser"
            self.set_focus(self._browser_table)
        elif event.data_table is self._playlist_table:
            self._focused_pane = "playlist"
            self.set_focus(self._playlist_table)
        event.stop()
        # Browser pane: mouse click toggles selection (like Space)
        if event.data_table is self._browser_table:
            entry = self._focused_browser_entry()
            if entry is None or entry.is_parent:
                return

            # Keep it simple for Stage 1: click toggles selection without clearing others.
            # (Shift-range / single-select behavior can be Stage 3 if you want.)
            self._browser.toggle_selection(entry)
            self._refresh_browser_entries()
            return

        # Playlist pane: mouse click toggles selection
        if event.data_table is self._playlist_table:
            index = self._focused_playlist_index()
            if index is None:
                return
            if index in self._playlist_selection:
                self._playlist_selection.remove(index)
            else:
                self._playlist_selection.add(index)
            self._refresh_playlist_entries()
            return

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table is self._browser_table:
            self._focused_pane = "browser"
            self.set_focus(self._browser_table)
        elif event.data_table is self._playlist_table:
            self._focused_pane = "playlist"
            self.set_focus(self._playlist_table)
        event.stop()

    def on_data_table_cell_selected(self, event: DataTable.CellSelected) -> None:
        if event.data_table is self._browser_table:
            self._focused_pane = "browser"
            self.set_focus(self._browser_table)
        elif event.data_table is self._playlist_table:
            self._focused_pane = "playlist"
            self.set_focus(self._playlist_table)
        event.stop()

    @staticmethod
    def _resolve_path(path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return path.absolute()


def _panel_wrapper(title: str, child: Container, *, panel_id: str) -> Container:
    panel = Container(child, id=panel_id)
    panel.border_title = title
    return panel


class DrivePrompt(ModalScreen[Optional[Path]]):
    """Modal prompt for selecting a drive/root."""

    def __init__(self, drives: list[Path]) -> None:
        super().__init__()
        self._drives = drives

    def compose(self) -> ComposeResult:
        options = [(str(path), str(path)) for path in self._drives]
        with Container(id="drive_prompt"):
            yield Static("Select Drive", id="drive_prompt_title")
            yield Select(options, id="drive_prompt_select")
            with Horizontal(id="drive_prompt_buttons"):
                yield Button("Connect", id="drive_prompt_ok")
                yield Button("Cancel", id="drive_prompt_cancel")

    def on_mount(self) -> None:
        select = self.query_one("#drive_prompt_select", Select)
        self.set_focus(select)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "drive_prompt_cancel":
            self.dismiss(None)
            return
        if event.button.id == "drive_prompt_ok":
            select = self.query_one("#drive_prompt_select", Select)
            value = select.value
            if value:
                self.dismiss(Path(str(value)))
            else:
                self.dismiss(None)
