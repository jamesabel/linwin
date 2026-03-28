"""Windows TUI Application — main Textual app for WSL2 setup."""

from __future__ import annotations

from textual.app import App

from ..shared.config import SetupConfig, load_config
from ..shared.theme import SHARED_CSS
from .screens.phase2 import Phase2Screen
from .screens.welcome import WelcomeScreen
from .tasks.state import clear_state, load_state


class WindowsSetupApp(App):
    """Textual TUI for WSL2 + Ubuntu + WSLg setup on Windows."""

    TITLE = "WSL2 Ubuntu Setup"
    CSS = SHARED_CSS

    BINDINGS = [
        ("ctrl+q", "quit", "Quit (Ctrl+Q)"),
        ("escape", "quit", "Quit (Escape)"),
    ]

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def on_mount(self) -> None:
        # Check for saved state from a pre-reboot Phase 1
        state = load_state()
        if state and state.phase1_complete and state.needs_reboot:
            # Post-reboot: go straight to Phase 2
            self.push_screen(Phase2Screen(self._config))
        else:
            self.push_screen(WelcomeScreen(self._config))


def check_admin() -> bool:
    """Check if running with admin privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def relaunch_as_admin() -> None:
    """Re-launch this module with admin privileges via UAC."""
    import ctypes
    import os
    import sys
    # Use -m to preserve relative imports; sys.argv may be a __main__.py
    # path which fails when run directly.
    args = "-m tui.windows"
    # Pass the current working directory so the elevated process can find
    # config.json and the tui package (ShellExecuteW defaults to System32).
    cwd = os.getcwd()
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        args, cwd, 1,  # SW_SHOWNORMAL
    )
