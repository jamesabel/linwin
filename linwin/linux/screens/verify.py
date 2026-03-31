"""Linux TUI Verification Screen."""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import run_local
from ...shared.widgets import VerifyDashboard


class VerifyScreen(Screen):
    """Linux verification dashboard."""

    BINDINGS = [
        ("escape", "quit_app", "Exit"),
    ]

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
        dash = self.query_one("#linux-verify", VerifyDashboard)
        status = self.query_one("#verify-status", Static)
        config = self._config

        # systemd
        result = await run_local("ps -p 1 -o comm= 2>/dev/null")
        is_systemd = result.output.strip() == "systemd"
        dash.add_check("systemd is PID 1", is_systemd, result.output.strip())

        # snapd
        result = await run_local("systemctl is-active snapd 2>/dev/null")
        snapd_ok = result.output.strip() == "active"
        dash.add_check("snapd service running", snapd_ok)

        # apt packages
        for pkg in config.aptPackages:
            result = await run_local(
                f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii' && echo yes || echo no"
            )
            dash.add_check(f"apt: {pkg}", result.output.strip() == "yes")

        # snap packages
        for snap in config.snaps:
            result = await run_local(
                f"snap list {snap.name} 2>/dev/null && echo yes || echo no"
            )
            dash.add_check(f"snap: {snap.name}", "yes" in result.output)

        # WSLg
        display = os.environ.get("DISPLAY", "")
        dash.add_check("DISPLAY set", bool(display), display, warn=not bool(display))

        result = await run_local("test -d /mnt/wslg && echo yes || echo no")
        wslg_dir = result.output.strip() == "yes"
        dash.add_check("/mnt/wslg exists", wslg_dir, warn=not wslg_dir)

        # V: drive mount
        dl = config.wslDriveLetter.lower()
        result = await run_local(f"test -d /mnt/{dl} && echo yes || echo no")
        mounted = result.output.strip() == "yes"
        dash.add_check(f"/mnt/{dl} mounted", mounted, warn=not mounted)

        # Summary
        if dash.all_passed:
            status.update("[green]All checks passed![/]")
        else:
            status.update("[yellow]Some checks need attention. See above.[/]")

    def action_quit_app(self) -> None:
        self.app.exit()

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if widget_id == "btn-exit":
            self.app.exit()
