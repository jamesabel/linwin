"""Windows TUI Launcher Screen — primary hub for launching WSL apps."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.launcher import WSL_APP_BUTTONS, launch_rdp, launch_windows_terminal, launch_wsl_app
from ...shared.subprocess_runner import run_wsl


class LauncherScreen(Screen):
    """Primary hub shown when Ubuntu is set up. Launch apps or run maintenance."""

    BINDINGS = [
        ("1", "launch_files", "File Manager"),
        ("2", "launch_pycharm", "PyCharm"),
        ("3", "launch_terminal", "Terminal"),
        ("4", "launch_rdp", "RDP"),
        ("5", "run_verify", "Verify"),
        ("6", "run_setup", "Setup"),
        ("7", "configure", "Configure"),
        ("8", "view_status", "Status"),
        ("9", "quit", "Exit"),
    ]

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
    .button-bar {
        height: auto;
        padding: 0 0;
    }
    .action-link {
        margin: 0 2;
        padding: 0 2;
        text-style: bold;
    }
    #btn-launch-files {
        color: $accent;
    }
    #btn-launch-pycharm {
        color: $accent;
    }
    #btn-launch-terminal {
        color: $accent;
    }
    #btn-rdp {
        color: $success;
    }
    #btn-verify {
        color: $text;
    }
    #btn-setup {
        color: $warning;
    }
    #btn-configure {
        color: $text;
    }
    #btn-status {
        color: $text;
    }
    #btn-exit {
        color: $text;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield Static("Ubuntu is ready", id="launcher-title")

            with Vertical(id="launch-section"):
                yield Static("Launch Applications", classes="section-header")
                with Vertical(classes="button-bar"):
                    yield Static("\\[1] Launch File Manager", id="btn-launch-files", classes="action-link")
                    yield Static("\\[2] Launch PyCharm", id="btn-launch-pycharm", classes="action-link")
                    yield Static("\\[3] Open Ubuntu Terminal", id="btn-launch-terminal", classes="action-link")
                    yield Static("\\[4] RDP into Ubuntu (XFCE4 Desktop)", id="btn-rdp", classes="action-link")

            with Vertical(id="maintenance-section"):
                yield Static("Maintenance", classes="maint-header")
                with Vertical(classes="button-bar"):
                    yield Static("\\[5] Run Verification", id="btn-verify", classes="action-link")
                    yield Static("\\[6] Re-run Setup", id="btn-setup", classes="action-link")
                    yield Static("\\[7] Configure Settings", id="btn-configure", classes="action-link")
                    yield Static("\\[8] View Status", id="btn-status", classes="action-link")
                    yield Static("\\[9] Exit", id="btn-exit", classes="action-link")

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if not widget_id:
            return
        if widget_id in WSL_APP_BUTTONS:
            cmd, display_name = WSL_APP_BUTTONS[widget_id]
            try:
                launch_wsl_app(self._config.distroImportName, cmd)
                self.app.notify(f"Launched: {display_name}")
            except Exception as e:
                self.app.notify(f"Failed to launch: {e}", severity="error")
        elif widget_id == "btn-launch-terminal":
            launch_windows_terminal()
        elif widget_id == "btn-rdp":
            self._launch_rdp()
        elif widget_id == "btn-verify":
            from .verify import VerifyScreen
            self.app.push_screen(VerifyScreen(self._config))
        elif widget_id == "btn-setup":
            from .setup import SetupScreen
            self.app.switch_screen(SetupScreen(self._config))
        elif widget_id == "btn-configure":
            from .config_editor import ConfigEditorScreen
            self.app.push_screen(ConfigEditorScreen(self._config))
        elif widget_id == "btn-status":
            self._go_to_status()
        elif widget_id == "btn-exit":
            self.app.exit()

    def action_launch_files(self) -> None:
        from ...shared.launcher import WSL_APP_BUTTONS, launch_wsl_app
        cmd, display_name = WSL_APP_BUTTONS["btn-launch-files"]
        try:
            launch_wsl_app(self._config.distroImportName, cmd)
            self.app.notify(f"Launched: {display_name}")
        except Exception as e:
            self.app.notify(f"Failed to launch: {e}", severity="error")

    def action_launch_pycharm(self) -> None:
        from ...shared.launcher import WSL_APP_BUTTONS, launch_wsl_app
        cmd, display_name = WSL_APP_BUTTONS["btn-launch-pycharm"]
        try:
            launch_wsl_app(self._config.distroImportName, cmd)
            self.app.notify(f"Launched: {display_name}")
        except Exception as e:
            self.app.notify(f"Failed to launch: {e}", severity="error")

    def action_launch_terminal(self) -> None:
        from ...shared.launcher import launch_windows_terminal
        launch_windows_terminal()

    def action_launch_rdp(self) -> None:
        self._launch_rdp()

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
        from ..tasks.health_check import run_health_check
        health = await run_health_check(self._config)
        from .status import StatusScreen
        self.app.switch_screen(StatusScreen(self._config, health))
