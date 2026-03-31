"""Windows TUI Launcher Screen — primary hub for launching WSL apps."""

from __future__ import annotations

import string

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import OptionList, Static
from textual import work

from ...shared.base_app import ClickDispatchScreen
from ...shared.config import AppEntry, SetupConfig
from ...shared.launcher import launch_rdp, launch_windows_terminal, notify_launch
from ...shared.subprocess_runner import run_wsl
from ..tasks.state import load_launcher_selection, save_launcher_selection


# Standard apps: always present. (action_name, label)
_STANDARD_APPS = [
    ("launch_files",    "Launch File Manager"),
    ("launch_terminal", "Open Ubuntu Terminal"),
    ("launch_rdp",      "RDP into Ubuntu (XFCE4 Desktop)"),
]

# Maintenance items: always present.
_MAINTENANCE = [
    ("run_verify",  "Run Verification"),
    ("run_setup",   "Re-run Setup"),
    ("configure",   "Configure Settings"),
    ("view_status", "View Status"),
    ("quit",        "Exit"),
]


def _app_action_name(app: AppEntry) -> str:
    """Derive a Textual action name from an AppEntry id."""
    return f"launch_app_{app.id.replace('-', '_')}"


class LauncherScreen(ClickDispatchScreen):
    """Primary hub shown when Ubuntu is set up. Launch apps or run maintenance.

    Uses two OptionList widgets for Tab-focusable, Enter-to-select navigation.
    Launch Applications use alpha keys (a-z), Maintenance uses numeric keys (1-5).
    """

    CSS = """
    #launcher-title {
        text-style: bold;
        color: $success;
        padding: 1 2;
        text-align: center;
    }
    #launch-section {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    #maintenance-section {
        border: ascii $secondary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    .section-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    .maint-header {
        text-style: bold;
        color: $secondary;
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

        # Build ordered lists of (action_name, label) for each section.
        self._launch_items: list[tuple[str, str]] = []
        for action, label in _STANDARD_APPS:
            self._launch_items.append((action, label))
        for app in self._optional_apps:
            self._launch_items.append((_app_action_name(app), f"Launch {app.display_name}"))

        self._maint_items: list[tuple[str, str]] = list(_MAINTENANCE)

    def on_mount(self) -> None:
        """Bind keys, restore last selection, and focus the launch list."""
        for i, (action, label) in enumerate(self._launch_items):
            if i < 26:
                key = string.ascii_lowercase[i]
                self._bindings.bind(key, action, label)
        for i, (action, label) in enumerate(self._maint_items):
            if i < 9:
                self._bindings.bind(str(i + 1), action, label)
        launch_list = self.query_one("#launch-list", OptionList)
        saved = load_launcher_selection()
        if 0 <= saved < launch_list.option_count:
            launch_list.highlighted = saved
        launch_list.focus()

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Ubuntu is ready", id="launcher-title")

            with Vertical(id="launch-section"):
                yield Static("Launch Applications", classes="section-header")
                launch_options = []
                for i, (_, label) in enumerate(self._launch_items):
                    key = string.ascii_lowercase[i] if i < 26 else " "
                    launch_options.append(f"[{key}] {label}")
                yield OptionList(*launch_options, id="launch-list")

            with Vertical(id="maintenance-section"):
                yield Static("Maintenance", classes="maint-header")
                maint_options = []
                for i, (_, label) in enumerate(self._maint_items):
                    maint_options.append(f"[{i + 1}] {label}")
                yield OptionList(*maint_options, id="maint-list")

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        """Persist the highlighted launch item for next session."""
        if event.option_list.id == "launch-list":
            save_launcher_selection(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Dispatch Enter-key selection from either OptionList."""
        list_id = event.option_list.id
        idx = event.option_index
        if list_id == "launch-list" and idx < len(self._launch_items):
            save_launcher_selection(idx)
            action_name = self._launch_items[idx][0]
            method = getattr(self, f"action_{action_name}", None)
            if method:
                method()
        elif list_id == "maint-list" and idx < len(self._maint_items):
            action_name = self._maint_items[idx][0]
            method = getattr(self, f"action_{action_name}", None)
            if method:
                method()

    # ── Standard app actions ─────────────────────────────────────────

    def action_launch_files(self) -> None:
        notify_launch(self.app, "nautilus", "File Manager", self._config.distroImportName)

    def action_launch_terminal(self) -> None:
        launch_windows_terminal()

    def action_launch_rdp(self) -> None:
        self._launch_rdp()

    # ── Maintenance actions ──────────────────────────────────────────

    def action_run_verify(self) -> None:
        from .verify import VerifyScreen
        self.app.push_screen(VerifyScreen(self._config))

    def action_run_setup(self) -> None:
        from .setup import SetupScreen
        self.app.switch_screen(SetupScreen(self._config))

    def action_configure(self) -> None:
        from .config_editor import ConfigEditorScreen
        self.app.push_screen(ConfigEditorScreen(self._config))

    def action_view_status(self) -> None:
        self._go_to_status()

    def action_quit(self) -> None:
        self.app.exit()

    # ── Dynamic optional-app dispatch ────────────────────────────────

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

    # ── Helpers ──────────────────────────────────────────────────────

    @work
    async def _launch_rdp(self) -> None:
        """Check that xrdp-sesman is active before launching the RDP client."""
        result = await run_wsl(
            self._config.distroImportName,
            "systemctl is-active xrdp 2>/dev/null && systemctl is-active xrdp-sesman 2>/dev/null",
        )
        if not result.success or "active" not in result.output:
            self.app.notify(
                "xrdp is not ready yet — wait a moment and try again",
                severity="warning",
            )
            return
        launch_rdp(self._config.xrdpPort, self._config.distroImportName)
        self.app.notify("Launched: Remote Desktop")

    @work
    async def _go_to_status(self) -> None:
        """Run health check and navigate to the status screen."""
        from ..tasks.health_check import run_health_check
        health = await run_health_check(self._config)
        from .status import StatusScreen
        self.app.switch_screen(StatusScreen(self._config, health))
