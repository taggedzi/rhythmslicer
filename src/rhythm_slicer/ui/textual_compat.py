from __future__ import annotations

try:
    from textual.containers import Container
    import textual.widgets as textual_widgets
    from textual.widget import Widget

    TextualPanel = getattr(textual_widgets, "Panel", None)

    class PanelFallback(Container):
        def __init__(
            self,
            *children: Widget,
            title: str | None = None,
            id: str | None = None,
            classes: str | None = None,
            disabled: bool = False,
        ) -> None:
            super().__init__(*children, id=id, classes=classes, disabled=disabled)
            if title:
                self.border_title = title

    Panel = TextualPanel or PanelFallback
except Exception as exc:  # pragma: no cover - depends on environment
    raise RuntimeError(
        "Textual is required for the TUI. Install the 'textual' dependency."
    ) from exc
