"""Linux TUI Application — main Textual app for WSL Ubuntu setup."""

from __future__ import annotations

from ..shared.base_app import BaseSetupApp
from .screens.welcome import WelcomeScreen


class LinuxSetupApp(BaseSetupApp):
    """Textual TUI for Ubuntu package setup inside WSL."""

    TITLE = "WSL Ubuntu Setup (Linux)"

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen(self._config))
