from __future__ import annotations

from textual import events
from textual.widgets import DataTable, Static


class VisualizerHud(Static):
    """Compact HUD for the visualizer pane."""


class PlaylistTable(DataTable):
    """Playlist table with double-click play behavior."""

    async def _on_click(self, event: events.Click) -> None:
        if hasattr(self.app, "_set_user_navigation_lockout"):
            self.app._set_user_navigation_lockout()
        await super()._on_click(event)

    def _on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if hasattr(self.app, "_set_user_navigation_lockout"):
            self.app._set_user_navigation_lockout()
        super()._on_mouse_scroll_down(event)

    def _on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if hasattr(self.app, "_set_user_navigation_lockout"):
            self.app._set_user_navigation_lockout()
        super()._on_mouse_scroll_up(event)
