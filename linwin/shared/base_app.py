"""Base Textual app and screen with shared bindings and click dispatch."""

from __future__ import annotations

from textual.app import App
from textual.screen import Screen

from .config import SetupConfig
from .theme import SHARED_CSS


class ClickDispatchScreen(Screen):
    """Base screen that dispatches on_click to action methods via a widget-ID map.

    Subclasses define ``CLICK_MAP``, a dict mapping widget IDs to action
    method names.  Clicks on mapped widgets are dispatched automatically,
    eliminating the need to duplicate action logic inside ``on_click``.

    Example::

        CLICK_MAP = {
            "btn-save": "save",
            "btn-cancel": "cancel",
        }

    A click on ``#btn-save`` calls ``self.action_save()``.
    """

    CLICK_MAP: dict[str, str] = {}

    def on_click(self, event) -> None:
        """Dispatch click events to action methods using CLICK_MAP."""
        widget_id = getattr(event.widget, "id", None)
        if not widget_id:
            return
        action_name = self.CLICK_MAP.get(widget_id)
        if action_name:
            method = getattr(self, f"action_{action_name}", None)
            if method:
                method()


class BaseSetupApp(App):
    """Base app with shared keybindings and clipboard support."""

    CSS = SHARED_CSS

    BINDINGS = [
        ("ctrl+q", "quit", "Quit (Ctrl+Q)"),
        ("escape", "quit", "Quit (Escape)"),
        ("ctrl+c", "copy_log", "Copy Log (Ctrl+C)"),
    ]

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def action_copy_log(self) -> None:
        """Copy the visible log panel content to the system clipboard."""
        from .widgets import LogPanel

        try:
            panel = self.screen.query_one(LogPanel)
            self.copy_to_clipboard(panel.get_text())
            self.notify("Log copied to clipboard")
        except Exception:
            pass
