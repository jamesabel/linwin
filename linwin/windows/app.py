"""Windows TUI Application — main Textual app for WSL2 setup."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ..shared.base_app import BaseSetupApp
from ..shared.setup_logging import get_logger
from .screens.setup import SetupScreen
from .tasks.state import load_state


class StartupScreen(Screen):
    """Lightweight screen shown during startup verification."""

    CSS = """
    #startup-title {
        text-style: bold;
        color: $primary;
        padding: 1 2;
        text-align: center;
    }
    #startup-status {
        padding: 0 2;
        color: $text;
    }
    #startup-checks {
        padding: 0 2;
        height: auto;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("WSL2 Ubuntu Setup", id="startup-title")
            yield Static("Running verification...", id="startup-status")
            yield Static("", id="startup-checks")

    def update_status(self, text: str) -> None:
        try:
            self.query_one("#startup-status", Static).update(text)
        except Exception:
            pass

    def add_check_result(self, name: str, passed: bool, warn: bool = False) -> None:
        try:
            tag = "[yellow]WARN[/]" if warn else ("[green]PASS[/]" if passed else "[red]FAIL[/]")
            checks = self.query_one("#startup-checks", Static)
            current = checks.renderable
            line = f"  {tag}  {name}"
            checks.update(f"{current}\n{line}" if current else line)
        except Exception:
            pass

    def show_summary(self, passed: int, failed: int, warnings: int) -> None:
        if failed == 0:
            self.update_status(
                f"[green]All checks passed[/] ({passed} passed, {warnings} warnings)"
            )
        else:
            self.update_status(
                f"[yellow]{failed} check(s) need attention[/] "
                f"({passed} passed, {warnings} warnings)"
            )


class WindowsSetupApp(BaseSetupApp):
    """Textual TUI for WSL2 + Ubuntu + WSLg setup on Windows."""

    TITLE = "WSL2 Ubuntu Setup"

    def on_mount(self) -> None:
        log = get_logger()
        state = load_state()
        if state and state.resume_from_task:
            log.info("Resuming after reboot -> SetupScreen (resume_from=%s, timestamp=%s)",
                     state.resume_from_task, state.timestamp)
            self.push_screen(SetupScreen(self._config, resume_from=state.resume_from_task))
        else:
            log.info("Running startup verification...")
            startup = StartupScreen()
            self.push_screen(startup)
            self._startup_check(startup)

    @work
    async def _startup_check(self, startup: StartupScreen) -> None:
        from .tasks.full_verify import VerifyCheckItem, run_full_verification
        log = get_logger()

        async def on_progress(item: VerifyCheckItem) -> None:
            startup.add_check_result(item.name, item.passed, item.warn)

        try:
            log.info("Running full verification...")
            verify_result = await run_full_verification(self._config, on_progress=on_progress)
        except Exception:
            log.exception("Verification crashed")
            self.exit(return_code=1, message="Verification failed — see log for details")
            return

        passed = sum(1 for c in verify_result.checks if c.passed and not c.warn)
        failed = len(verify_result.failed_checks)
        warnings = sum(1 for c in verify_result.checks if c.warn)
        startup.show_summary(passed, failed, warnings)

        if verify_result.all_passed:
            log.info("All checks passed -> LauncherScreen")
            import asyncio
            await asyncio.sleep(1.5)  # brief pause to show success
            from .screens.launcher import LauncherScreen
            self.switch_screen(LauncherScreen(self._config))
        else:
            log.info("Setup needed (%d failures), detecting system profile...", failed)
            startup.update_status(
                f"[yellow]{failed} check(s) need attention[/] — detecting system..."
            )
            try:
                from .tasks.auto_config import build_auto_config, detect_system_profile
                profile = await detect_system_profile()
                auto_config = build_auto_config(profile, self._config)
                log.info("Auto-config: drive=%s memory=%s cpus=%d vhd=%s",
                         auto_config.wslDriveLetter, auto_config.wslconfig.memory,
                         auto_config.wslconfig.processors, auto_config.wslconfig.defaultVhdSize)
                from .screens.setup_proposal import SetupProposalScreen
                self.switch_screen(SetupProposalScreen(auto_config, profile, verify_result))
            except Exception:
                log.exception("Auto-config crashed, falling back to StatusScreen")
                from .tasks.health_check import run_health_check
                health = await run_health_check(self._config)
                from .screens.status import StatusScreen
                self.switch_screen(StatusScreen(self._config, health))


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
    args = "-m linwin.windows"
    # Pass the current working directory so the elevated process can find
    # config.json and the linwin package (ShellExecuteW defaults to System32).
    cwd = os.getcwd()
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable,
        args, cwd, 1,  # SW_SHOWNORMAL
    )
