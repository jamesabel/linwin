"""Windows TUI Application — main Textual app for WSL2 setup."""

from __future__ import annotations

from textual import work

from ..shared.base_app import BaseSetupApp
from ..shared.setup_logging import get_logger
from .screens.setup import SetupScreen
from .tasks.state import load_state


class WindowsSetupApp(BaseSetupApp):
    """Textual TUI for WSL2 + Ubuntu + WSLg setup on Windows."""

    TITLE = "WSL2 Ubuntu Setup"

    def on_mount(self) -> None:
        log = get_logger()
        # Check for saved state from a pre-reboot run
        state = load_state()
        if state and state.resume_from_task:
            log.info("Resuming after reboot -> SetupScreen (resume_from=%s, timestamp=%s)",
                     state.resume_from_task, state.timestamp)
            self.push_screen(SetupScreen(self._config, resume_from=state.resume_from_task))
        else:
            log.info("Running startup health check...")
            self._startup_check()

    @work
    async def _startup_check(self) -> None:
        from .tasks.health_check import run_health_check
        log = get_logger()
        health = await run_health_check(self._config)
        if health.ready:
            log.info("Health check passed -> LauncherScreen")
            from .screens.launcher import LauncherScreen
            self.push_screen(LauncherScreen(self._config))
        else:
            log.info("Health check failed -> StatusScreen")
            from .screens.status import StatusScreen
            self.push_screen(StatusScreen(self._config, health))


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
