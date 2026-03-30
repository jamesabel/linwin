"""Linux TUI Welcome Screen — system info and config summary."""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Label, Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import run_local


class WelcomeScreen(Screen):
    """Welcome screen with Linux system detection."""

    CSS = """
    #welcome-info {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    #welcome-config {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    .info-row {
        height: 1;
        layout: horizontal;
    }
    .info-row Label:first-child {
        width: 24;
        text-style: bold;
    }
    .section-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
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
    }
    #btn-configure {
        color: $text;
    }
    #btn-start {
        color: $success;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            with Vertical(id="welcome-info"):
                yield Static("System Information", classes="section-header")
                yield Label("Detecting...", id="detecting-label")

            with Vertical(id="welcome-config"):
                yield Static("Current Configuration", classes="section-header")
                c = self._config
                yield _info_row("Apt Packages:", ", ".join(c.aptPackages))
                snap_names = ", ".join(s.name for s in c.snaps)
                yield _info_row("Snaps:", snap_names)
                yield _info_row("Enable Systemd:", "Yes" if c.enableSystemd else "No")

            with Vertical(classes="button-bar"):
                yield Static(">> Configure Settings <<", id="btn-configure", classes="action-link")
                yield Static(">> Start Setup <<", id="btn-start", classes="action-link")
                yield Static(">> Quit (Escape) <<", id="btn-quit", classes="action-link")

    def on_mount(self) -> None:
        self.detect_system_info()

    @work(exclusive=True)
    async def detect_system_info(self) -> None:
        info_box = self.query_one("#welcome-info")
        detecting = self.query_one("#detecting-label")

        # Ubuntu version
        result = await run_local("lsb_release -ds 2>/dev/null || cat /etc/os-release 2>/dev/null | head -1")
        ubuntu_ver = result.output.strip().split("\n")[0] if result.success else "Unknown"

        # Kernel
        result = await run_local("uname -r")
        kernel = result.output.strip() if result.success else "Unknown"

        # systemd status
        result = await run_local("ps -p 1 -o comm= 2>/dev/null")
        init_system = result.output.strip() if result.success else "unknown"
        systemd_ok = init_system == "systemd"

        # snapd
        result = await run_local("systemctl is-active snapd 2>/dev/null")
        snapd_ok = result.output.strip() == "active"

        # DISPLAY
        display = os.environ.get("DISPLAY", "")

        # /mnt/wslg
        result = await run_local("test -d /mnt/wslg && echo yes || echo no")
        wslg_dir = result.output.strip() == "yes"

        # Remove detecting label and add results
        detecting.remove()

        rows = [
            ("OS:", ubuntu_ver, None),
            ("Kernel:", kernel, None),
            ("Init System:", init_system, systemd_ok),
            ("Snapd:", "active" if snapd_ok else "inactive", snapd_ok),
            ("DISPLAY:", display or "(not set)", bool(display)),
            ("/mnt/wslg:", "exists" if wslg_dir else "not found", wslg_dir),
        ]

        for label_text, value_text, ok in rows:
            if ok is None:
                status_str = ""
            elif ok:
                status_str = "  [green]OK[/]"
            else:
                status_str = "  [yellow]![/]"
            row = Horizontal(classes="info-row")
            await info_box.mount(row)
            await row.mount(Label(label_text))
            await row.mount(Label(f"{value_text}{status_str}"))

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if not widget_id:
            return
        if widget_id == "btn-configure":
            from .config_editor import ConfigEditorScreen
            self.app.push_screen(ConfigEditorScreen(self._config))
        elif widget_id == "btn-start":
            from .setup import SetupScreen
            self.app.push_screen(SetupScreen(self._config))
        elif widget_id == "btn-quit":
            self.app.exit()


def _info_row(label: str, value: str) -> Horizontal:
    row = Horizontal(classes="info-row")
    row.compose_add_child(Label(label))
    row.compose_add_child(Label(value))
    return row
