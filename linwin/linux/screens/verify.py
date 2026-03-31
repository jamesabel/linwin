"""Linux TUI Verification Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static
from textual import work

from ...shared.base_app import ClickDispatchScreen
from ...shared.config import SetupConfig
from ...shared.subprocess_runner import run_local
from ...shared.verify_checks import (
    check_apt_package,
    check_display_set,
    check_drive_mounted,
    check_snap_package,
    check_snapd,
    check_systemd,
    check_wslg_dir,
)
from ...shared.widgets import VerifyDashboard


class VerifyScreen(ClickDispatchScreen):
    """Linux verification dashboard."""

    BINDINGS = [
        ("escape", "quit_app", "Exit"),
    ]

    CLICK_MAP = {
        "btn-exit": "quit_app",
    }

    CSS = """
    #verify-status {
        padding: 1 2;
        text-style: bold;
    }
    .button-bar {
        height: auto;
        padding: 1 2;
        align-horizontal: center;
    }
    .action-link {
        margin: 0 2;
        padding: 0 2;
        text-style: bold;
        color: $text;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield VerifyDashboard(title="Linux Verification", id="linux-verify")
            yield Static("Running verification...", id="verify-status")
            with Horizontal(classes="button-bar"):
                yield Static("\\[Esc] Exit", id="btn-exit", classes="action-link")

    def on_mount(self) -> None:
        self.run_verification()

    @work(exclusive=True)
    async def run_verification(self) -> None:
        """Run all Linux verification checks and populate the dashboard."""
        dash = self.query_one("#linux-verify", VerifyDashboard)
        status = self.query_one("#verify-status", Static)
        config = self._config

        is_systemd, init_name = await check_systemd(run_local)
        dash.add_check("systemd is PID 1", is_systemd, init_name)

        dash.add_check("snapd service running", await check_snapd(run_local))

        for pkg in config.aptPackages:
            dash.add_check(f"apt: {pkg}", await check_apt_package(run_local, pkg))

        for app in config.optionalApps:
            if app.install_method == "snap":
                dash.add_check(f"snap: {app.id}", await check_snap_package(run_local, app.id))
            elif app.install_method == "apt":
                dash.add_check(f"apt: {app.id}", await check_apt_package(run_local, app.id))

        display_ok, display_val = await check_display_set()
        dash.add_check("DISPLAY set", display_ok, display_val, warn=not display_ok)

        wslg_dir = await check_wslg_dir(run_local)
        dash.add_check("/mnt/wslg exists", wslg_dir, warn=not wslg_dir)

        dl = config.wslDriveLetter.lower()
        mounted = await check_drive_mounted(run_local, config.wslDriveLetter)
        dash.add_check(f"/mnt/{dl} mounted", mounted, warn=not mounted)

        if dash.all_passed:
            status.update("[green]All checks passed![/]")
        else:
            status.update("[yellow]Some checks need attention. See above.[/]")

    def action_quit_app(self) -> None:
        self.app.exit()
