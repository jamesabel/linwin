"""Base Textual app with shared bindings and actions."""

from __future__ import annotations

from textual.app import App

from .config import SetupConfig
from .theme import SHARED_CSS


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
