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
        ("q", "quit", "Quit"),
    ]

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen(self._config))
