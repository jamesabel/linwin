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
        ("q", "quit", "Quit"),
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
    """Re-launch this script with admin privileges via UAC."""
    import ctypes
    import sys
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        " ".join(f'"{a}"' for a in sys.argv),
        None, 1,  # SW_SHOWNORMAL
    )
