"""Windows TUI Verification Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import Static
from textual import work

from ...shared.base_app import ClickDispatchScreen
from ...shared.config import SetupConfig
from ...shared.launcher import launch_windows_terminal, notify_launch
from ...shared.widgets import VerifyDashboard
from ..tasks.full_verify import run_full_verification


class VerifyScreen(ClickDispatchScreen):
    """Verification dashboard showing PASS/FAIL/WARN for all checks."""

    BINDINGS = [
        ("1", "go_launcher", "Launcher"),
        ("2", "launch_files", "Files"),
        ("3", "launch_pycharm", "PyCharm"),
        ("4", "launch_terminal", "Terminal"),
        ("5", "quit", "Exit"),
    ]

    CLICK_MAP = {
        "btn-launcher": "go_launcher",
        "btn-launch-files": "launch_files",
        "btn-launch-pycharm": "launch_pycharm",
        "btn-launch-terminal": "launch_terminal",
        "btn-exit": "quit",
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
    #btn-launch-files {
        color: $accent;
    }
    #btn-launch-terminal {
        color: $accent;
    }
    #btn-launcher {
        color: $accent;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield VerifyDashboard(title="Windows Checks", id="win-verify")
            yield VerifyDashboard(title="Linux Checks", id="linux-verify")
            yield Static("Running verification...", id="verify-status")
            with Horizontal(classes="button-bar"):
                yield Static("\\[1] Back to Launcher", id="btn-launcher", classes="action-link")
                yield Static("\\[2] Launch File Manager", id="btn-launch-files", classes="action-link")
                yield Static("\\[3] Launch PyCharm", id="btn-launch-pycharm", classes="action-link")
                yield Static("\\[4] Open Ubuntu Terminal", id="btn-launch-terminal", classes="action-link")
                yield Static("\\[5] Exit", id="btn-exit", classes="action-link")

    def on_mount(self) -> None:
        self.run_verification()

    @work(exclusive=True)
    async def run_verification(self) -> None:
        """Run full verification and populate both dashboards."""
        win_dash = self.query_one("#win-verify", VerifyDashboard)
        linux_dash = self.query_one("#linux-verify", VerifyDashboard)
        status = self.query_one("#verify-status", Static)

        result = await run_full_verification(self._config)

        for item in result.checks:
            dash = linux_dash if item.category == "linux" else win_dash
            dash.add_check(item.name, item.passed, item.detail, warn=item.warn)

        total_failed = len(result.failed_checks)
        if total_failed == 0:
            status.update("[green]All checks passed![/]")
        else:
            status.update(f"[red]{total_failed} check(s) failed. See details above.[/]")

    def action_go_launcher(self) -> None:
        from .launcher import LauncherScreen
        self.app.switch_screen(LauncherScreen(self._config))

    def action_launch_files(self) -> None:
        notify_launch(self.app, "btn-launch-files", self._config.distroImportName)

    def action_launch_pycharm(self) -> None:
        notify_launch(self.app, "btn-launch-pycharm", self._config.distroImportName)

    def action_launch_terminal(self) -> None:
        launch_windows_terminal()

    def action_quit(self) -> None:
        self.app.exit()
