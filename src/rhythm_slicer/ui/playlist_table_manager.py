from __future__ import annotations

from typing import TYPE_CHECKING
import logging

from rich.text import Text
from textual.widgets.data_table import RowDoesNotExist

from rhythm_slicer.playlist import Track
from rhythm_slicer.ui.tui_formatters import ellipsize

if TYPE_CHECKING:
    from rhythm_slicer.tui import RhythmSlicerApp

logger = logging.getLogger("rhythm_slicer.tui")


class PlaylistTableManager:
    def __init__(self, app: "RhythmSlicerApp") -> None:
        self._app = app

    def _init_playlist_table(self) -> None:
        if not self._app._playlist_table:
            return
        self._app._playlist_table.clear(columns=True)
        self._app._playlist_table.add_column(
            "Title", key=self._app._playlist_title_column
        )
        self._app._playlist_table.add_column(
            "Artist", key=self._app._playlist_artist_column
        )
        self._app._playlist_table.cursor_type = "row"
        self._app._playlist_table.show_cursor = True
        self._app._playlist_table.zebra_stripes = False
        self._app._playlist_table_width = 0
        self._app._playlist_title_max = 0
        self._app._playlist_artist_max = 0
        self._app._playing_key = None
        self._app._selected_key = None

    def _refresh_playlist_table_after_layout(self) -> None:
        if self._playlist_table_content_width() <= 0:
            self._app.set_timer(0.05, self._refresh_playlist_table_after_layout)
            return
        self._refresh_playlist_table(rebuild=True)

    def _playlist_row_key(self, index: int) -> str:
        return str(index)

    def _playlist_table_content_width(self) -> int:
        if not self._app._playlist_table:
            return 0
        size = getattr(self._app._playlist_table, "content_size", None) or getattr(
            self._app._playlist_table, "size", None
        )
        width = getattr(size, "width", 0) if size else 0
        return max(0, width)

    def _playlist_table_limits(self) -> tuple[int, int, int]:
        width = self._playlist_table_content_width()
        if width <= 0:
            width = self._app._playlist_table_width or 40
        if not self._app._playlist_table:
            return width, 0, 0
        gutter = 6  # padding/scrollbar cushion to avoid a horizontal scrollbar
        usable_width = width - gutter if width > gutter else width
        if usable_width <= 0:
            return width, 0, 0
        min_title = 1 if usable_width > 0 else 0
        min_artist = 1 if usable_width > 1 else 0
        title_max = max(min_title, int(usable_width * 0.6))
        artist_max = max(min_artist, usable_width - title_max)
        total = title_max + artist_max
        if total < usable_width:
            artist_max += usable_width - total
        elif total > usable_width:
            overflow = total - usable_width
            trim_title = min(overflow, max(0, title_max - min_title))
            title_max -= trim_title
            overflow -= trim_title
            if overflow > 0:
                artist_max = max(min_artist, artist_max - overflow)
        return width, title_max, artist_max

    def _playlist_row_cells(
        self,
        track: Track,
        *,
        is_playing: bool,
        title_max: int,
        artist_max: int,
    ) -> tuple[Text, Text]:
        meta = self._app._get_track_meta_cached(track.path)
        if meta is None:
            self._app._ensure_track_meta_loaded(track.path)
        title = (meta.title if meta else None) or track.title or track.path.name
        artist = (meta.artist if meta else None) or "Unknown"
        title = ellipsize(title, title_max)
        artist = ellipsize(artist, artist_max)
        if is_playing:
            style = "bold #5fc9d6"
            return Text(title, style=style), Text(artist, style=style)
        return Text(title), Text(artist)

    def _move_table_cursor(self, row_index: int) -> None:
        if not self._app._playlist_table:
            return
        if self._app._playlist_table.cursor_row == row_index:
            return
        self._app._suppress_table_events = True
        try:
            self._app._playlist_table.move_cursor(row=row_index, column=0, scroll=False)
        finally:
            self._app._suppress_table_events = False

    def _restore_table_cursor_from_selected(self) -> None:
        if not self._app._playlist_table:
            return
        if not self._app._selected_key:
            return
        try:
            row_index = self._app._playlist_table.get_row_index(self._app._selected_key)
        except RowDoesNotExist:
            if self._app._selected_key not in self._app._missing_row_keys_logged:
                self._app._missing_row_keys_logged.add(self._app._selected_key)
                logger.warning("Playlist row key missing: %s", self._app._selected_key)
            return
        self._move_table_cursor(row_index)

    def _refresh_playlist_table(self, *, rebuild: bool = False) -> None:
        if not self._app._playlist_table:
            return
        if not self._app.playlist or self._app.playlist.is_empty():
            if self._app._playlist_table.row_count:
                self._app._playlist_table.clear()
            self._app._playlist_table_source = self._app.playlist
            self._app._playing_key = None
            self._app._selected_key = None
            return
        width, title_max, artist_max = self._playlist_table_limits()
        width_changed = width != self._app._playlist_table_width
        tracks = self._app.playlist.tracks
        if (
            rebuild
            or self._app._playlist_table_source is not self._app.playlist
            or self._app._playlist_table.row_count != len(tracks)
            or width_changed
        ):
            self._app._playlist_table.clear(columns=True)
            self._app._playlist_table.add_column(
                "Title",
                key=self._app._playlist_title_column,
                width=title_max,
            )
            self._app._playlist_table.add_column(
                "Artist",
                key=self._app._playlist_artist_column,
                width=artist_max,
            )
            for idx, track in enumerate(tracks):
                title_cell, artist_cell = self._playlist_row_cells(
                    track,
                    is_playing=(idx == self._app._playing_index),
                    title_max=title_max,
                    artist_max=artist_max,
                )
                self._app._playlist_table.add_row(
                    title_cell,
                    artist_cell,
                    key=self._playlist_row_key(idx),
                )
            self._app._playlist_table_source = self._app.playlist
            self._app._playlist_table_width = width
            self._app._playlist_title_max = title_max
            self._app._playlist_artist_max = artist_max
            self._app._playing_key = (
                self._playlist_row_key(self._app._playing_index)
                if self._app._playing_index is not None
                else None
            )
            self._restore_table_cursor_from_selected()
        else:
            if width_changed:
                for idx, track in enumerate(tracks):
                    row_key = self._playlist_row_key(idx)
                    title_cell, artist_cell = self._playlist_row_cells(
                        track,
                        is_playing=(idx == self._app._playing_index),
                        title_max=title_max,
                        artist_max=artist_max,
                    )
                    self._app._playlist_table.update_cell(
                        row_key,
                        self._app._playlist_title_column,
                        title_cell,
                    )
                    self._app._playlist_table.update_cell(
                        row_key,
                        self._app._playlist_artist_column,
                        artist_cell,
                    )
                self._app._playlist_table_width = width
                self._app._playlist_title_max = title_max
                self._app._playlist_artist_max = artist_max
                self._app._playing_key = (
                    self._playlist_row_key(self._app._playing_index)
                    if self._app._playing_index is not None
                    else None
                )
                self._restore_table_cursor_from_selected()
            else:
                self._update_playing_row_style()

    def _update_playing_row_style(self) -> None:
        if not self._app._playlist_table or not self._app.playlist:
            return
        new_key = (
            self._playlist_row_key(self._app._playing_index)
            if self._app._playing_index is not None
            else None
        )
        if new_key == self._app._playing_key:
            return
        width, title_max, artist_max = self._playlist_table_limits()
        self._app._playlist_table_width = width
        self._app._playlist_title_max = title_max
        self._app._playlist_artist_max = artist_max

        if self._app._playing_key is not None:
            try:
                old_index = int(self._app._playing_key)
            except (TypeError, ValueError):
                old_index = None
            if (
                old_index is not None
                and self._app.playlist
                and 0 <= old_index < len(self._app.playlist.tracks)
            ):
                track = self._app.playlist.tracks[old_index]
                title_cell, artist_cell = self._playlist_row_cells(
                    track,
                    is_playing=False,
                    title_max=title_max,
                    artist_max=artist_max,
                )
                self._update_row_cells(self._app._playing_key, title_cell, artist_cell)
        if new_key is not None:
            try:
                new_index = int(new_key)
            except (TypeError, ValueError):
                new_index = None
            if (
                new_index is not None
                and self._app.playlist
                and 0 <= new_index < len(self._app.playlist.tracks)
            ):
                track = self._app.playlist.tracks[new_index]
                title_cell, artist_cell = self._playlist_row_cells(
                    track,
                    is_playing=True,
                    title_max=title_max,
                    artist_max=artist_max,
                )
                self._update_row_cells(new_key, title_cell, artist_cell)
        self._app._playing_key = new_key

    def _update_row_cells(
        self,
        row_key: str,
        title_cell: Text,
        artist_cell: Text,
    ) -> bool:
        if not self._app._playlist_table:
            return False
        try:
            self._app._playlist_table.update_cell(
                row_key,
                self._app._playlist_title_column,
                title_cell,
            )
            self._app._playlist_table.update_cell(
                row_key,
                self._app._playlist_artist_column,
                artist_cell,
            )
            return True
        except RowDoesNotExist:
            if row_key not in self._app._missing_row_keys_logged:
                self._app._missing_row_keys_logged.add(row_key)
                logger.warning("Playlist row key missing: %s", row_key)
            return False

    def _set_selected(
        self,
        index: int,
        *,
        move_cursor: bool = True,
        update_selected_key: bool = True,
    ) -> None:
        if not self._app.playlist or self._app.playlist.is_empty():
            return
        index = max(0, min(index, len(self._app.playlist.tracks) - 1))
        self._app.playlist.set_index(index)
        self._app._sync_play_order_pos()
        if update_selected_key:
            self._app._selected_key = self._playlist_row_key(index)
        if move_cursor:
            self._move_table_cursor(index)
        self._app._update_playlist_view()
