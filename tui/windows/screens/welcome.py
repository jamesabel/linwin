"""Windows TUI Welcome Screen — system info and config summary."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static
from textual import work

from ...shared.config import SetupConfig
from ..tasks import validators


class WelcomeScreen(Screen):
    """Welcome screen with system detection and config summary."""

    CSS = """
    #welcome-info {
        border: solid $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    #welcome-config {
        border: solid $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    #welcome-info .info-row {
        height: 1;
        layout: horizontal;
    }
    #welcome-info .info-row Label:first-child {
        width: 24;
        text-style: bold;
    }
    #welcome-config .config-row {
        height: 1;
        layout: horizontal;
    }
    #welcome-config .config-row Label:first-child {
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
    .button-bar Button {
        margin: 0 2;
    }
    #detecting-label {
        margin: 1 3;
        color: $warning;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            with Vertical(id="welcome-info"):
                yield Static("System Information", classes="section-header")
                yield Label("Detecting system info...", id="detecting-label")

            with Vertical(id="welcome-config"):
                yield Static("Current Configuration", classes="section-header")
                c = self._config
                wc = c.wslconfig
                yield _config_row("Distro:", c.distroName)
                yield _config_row("Import Name:", c.distroImportName)
                yield _config_row("Install Path:", c.wslInstallPath)
                yield _config_row("Memory:", wc.memory)
                yield _config_row("Processors:", str(wc.processors))
                yield _config_row("Swap:", wc.swap)
                yield _config_row("VHD Size:", wc.defaultVhdSize)
                snap_names = ", ".join(s.name for s in c.snaps)
                yield _config_row("Snaps:", snap_names)
                yield _config_row("Apt Packages:", ", ".join(c.aptPackages))

            with Horizontal(classes="button-bar"):
                yield Button("Configure Settings", id="btn-configure", variant="default")
                yield Button("Start Setup", id="btn-start", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.detect_system_info()

    @work(exclusive=True)
    async def detect_system_info(self) -> None:
        info_box = self.query_one("#welcome-info")
        detecting = self.query_one("#detecting-label")

        # Run all checks
        build = await validators.check_windows_build()
        virt = await validators.check_virtualization()
        ram = await validators.check_ram()
        cpus = await validators.check_cpu_count()
        drive = await validators.check_drive_exists(self._config.wslDriveLetter)

        # Replace the detecting label with results
        detecting.remove()

        rows = [
            ("Windows Build:", build.message, build.ok),
            ("Virtualization:", virt.message, virt.ok),
            ("RAM:", ram.message, True),
            ("CPUs:", cpus.message, True),
            (f"Drive {self._config.wslDriveLetter}:", f"{drive.message} ({drive.detail})" if drive.detail else drive.message, drive.ok),
        ]

        for label_text, value_text, ok in rows:
            status = "[green]OK[/]" if ok else "[red]FAIL[/]"
            row = Horizontal(classes="info-row")
            await info_box.mount(row)
            await row.mount(Label(label_text))
            await row.mount(Label(f"{value_text}  {status}"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-configure":
            from .config_editor import ConfigEditorScreen
            self.app.push_screen(ConfigEditorScreen(self._config))
        elif event.button.id == "btn-start":
            from .phase1 import Phase1Screen
            self.app.push_screen(Phase1Screen(self._config))


def _config_row(label: str, value: str) -> Horizontal:
    row = Horizontal(classes="config-row")
    row.compose_add_child(Label(label))
    row.compose_add_child(Label(value))
    return row
