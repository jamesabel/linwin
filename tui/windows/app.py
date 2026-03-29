"""Windows TUI Application — main Textual app for WSL2 setup."""

from __future__ import annotations

from textual.app import App

from ..shared.config import SetupConfig, load_config
from ..shared.setup_logging import get_logger
from ..shared.theme import SHARED_CSS
from .screens.setup import SetupScreen
from .screens.welcome import WelcomeScreen
from .tasks.state import load_state


class WindowsSetupApp(App):
    """Textual TUI for WSL2 + Ubuntu + WSLg setup on Windows."""

    TITLE = "WSL2 Ubuntu Setup"
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
        log = get_logger()
        # Check for saved state from a pre-reboot run
        state = load_state()
        if state and state.resume_from_task:
            log.info("Resuming after reboot -> SetupScreen (resume_from=%s, timestamp=%s)",
                     state.resume_from_task, state.timestamp)
            self.push_screen(SetupScreen(self._config, resume_from=state.resume_from_task))
        else:
            log.info("Starting fresh -> Welcome screen")
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
