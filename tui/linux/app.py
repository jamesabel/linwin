"""Linux TUI Application — main Textual app for WSL Ubuntu setup."""

from __future__ import annotations

from textual.app import App

from ..shared.config import SetupConfig
from ..shared.theme import SHARED_CSS
from .screens.welcome import WelcomeScreen


class LinuxSetupApp(App):
    """Textual TUI for Ubuntu package setup inside WSL."""

    TITLE = "WSL Ubuntu Setup (Linux)"
    CSS = SHARED_CSS

    BINDINGS = [
        ("ctrl+q", "quit", "Quit (Ctrl+Q)"),
        ("escape", "quit", "Quit (Escape)"),
        ("ctrl+c", "copy_log", "Copy Log (Ctrl+C)"),
    ]

    def action_copy_log(self) -> None:
        """Copy the visible log panel content to the system clipboard."""
        from ..shared.widgets import LogPanel
        try:
            panel = self.screen.query_one(LogPanel)
            self.copy_to_clipboard(panel.get_text())
            self.notify("Log copied to clipboard")
        except Exception:
            pass

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen(self._config))
