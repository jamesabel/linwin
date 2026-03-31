"""Windows TUI Verification Screen."""

from __future__ import annotations

import string

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import OptionList, Static
from textual import work

from ...shared.base_app import ClickDispatchScreen
from ...shared.config import AppEntry, SetupConfig
from ...shared.launcher import launch_windows_terminal, notify_launch
from ...shared.widgets import VerifyDashboard
from ..tasks.full_verify import run_full_verification


def _app_action_name(app: AppEntry) -> str:
    """Derive a Textual action name from an AppEntry id."""
    return f"launch_app_{app.id.replace('-', '_')}"


class VerifyScreen(ClickDispatchScreen):
    """Verification dashboard showing PASS/FAIL/WARN for all checks.

    Uses OptionList widgets for Tab-focusable, Enter-to-select navigation.
    """

    CSS = """
    #verify-status {
        padding: 1 2;
        text-style: bold;
    }
    #actions-section {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    .section-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    OptionList {
        height: auto;
        border: none;
        padding: 0;
        background: $surface;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._optional_apps = config.optionalApps

        # Build action items: launcher, file manager, optional apps, terminal, exit
        self._action_items: list[tuple[str, str]] = [
            ("go_launcher", "Back to Launcher"),
            ("launch_files", "Launch File Manager"),
        ]
        for app in self._optional_apps:
            self._action_items.append((_app_action_name(app), f"Launch {app.display_name}"))
        self._action_items.append(("launch_terminal", "Open Ubuntu Terminal"))
        self._action_items.append(("quit", "Exit"))

    def on_mount(self) -> None:
        """Bind alpha keys for actions."""
        for i, (action, label) in enumerate(self._action_items):
            if i < 26:
                key = string.ascii_lowercase[i]
                self._bindings.bind(key, action, label)

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield VerifyDashboard(title="Windows Checks", id="win-verify")
            yield VerifyDashboard(title="Linux Checks", id="linux-verify")
            yield Static("Running verification...", id="verify-status")
            with Vertical(id="actions-section"):
                yield Static("Actions", classes="section-header")
                options = []
                for i, (_, label) in enumerate(self._action_items):
                    key = string.ascii_lowercase[i] if i < 26 else " "
                    options.append(f"[{key}] {label}")
                yield OptionList(*options, id="verify-actions")

    def on_screen_show(self) -> None:
        """Run verification when first shown."""
        self.run_verification()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Dispatch Enter-key selection from the OptionList."""
        idx = event.option_index
        if idx < len(self._action_items):
            action_name = self._action_items[idx][0]
            method = getattr(self, f"action_{action_name}", None)
            if method:
                method()

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

    # ── Actions ──────────────────────────────────────────────────────

    def action_go_launcher(self) -> None:
        from .launcher import LauncherScreen
        self.app.switch_screen(LauncherScreen(self._config))

    def action_launch_files(self) -> None:
        notify_launch(self.app, "nautilus", "File Manager", self._config.distroImportName)

    def action_launch_terminal(self) -> None:
        launch_windows_terminal()

    def action_quit(self) -> None:
        self.app.exit()

    def __getattr__(self, name: str):
        """Handle action_launch_app_<id> calls for optional apps."""
        if name.startswith("action_launch_app_"):
            app_id = name[len("action_launch_app_"):].replace("_", "-")
            for entry in self._optional_apps:
                if entry.id == app_id:
                    return lambda: notify_launch(
                        self.app, entry.command, entry.display_name,
                        self._config.distroImportName,
                    )
        raise AttributeError(name)
