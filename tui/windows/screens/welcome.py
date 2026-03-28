"""Windows TUI Welcome Screen — system info and config summary."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, Footer, Header, Label, Static
from textual import work

from ...shared.config import SetupConfig
from ..tasks import validators


class DetailModal(ModalScreen):
    """Modal that shows the detail text for a failed check."""

    CSS = """
    DetailModal {
        align: center middle;
    }
    #detail-dialog {
        width: 80;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    #detail-title {
        text-style: bold;
        color: $error;
        margin-bottom: 1;
    }
    #detail-text {
        height: auto;
        margin-bottom: 1;
    }
    #detail-close {
        width: 100%;
    }
    """

    def __init__(self, title: str, detail: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._detail = detail

    def compose(self) -> ComposeResult:
        with Vertical(id="detail-dialog"):
            yield Static(self._title, id="detail-title")
            yield Static(self._detail, id="detail-text")
            yield Button("Close", id="detail-close", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss()


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
    .info-row-fail {
        color: $error;
    }
    .info-row-fail-btn {
        min-width: 16;
        margin: 0 0 0 1;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._fail_details: dict[str, tuple[str, str]] = {}  # button_id -> (title, detail)

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

        checks = [
            ("build", "Windows Build:", build),
            ("virt", "Virtualization:", virt),
            ("ram", "RAM:", ram),
            ("cpus", "CPUs:", cpus),
            ("drive", f"Drive {self._config.wslDriveLetter}:", drive),
        ]

        for check_id, label_text, result in checks:
            if result.ok:
                display = f"{result.message}  [green]OK[/]"
                if result.detail and result.detail != "OK":
                    display = f"{result.message} ({result.detail})  [green]OK[/]"
                row = Horizontal(classes="info-row")
                await info_box.mount(row)
                await row.mount(Label(label_text))
                await row.mount(Label(display))
            else:
                row = Horizontal(classes="info-row")
                await info_box.mount(row)
                await row.mount(Label(label_text))
                await row.mount(Label(f"{result.message}  [red]FAIL[/]"))
                if result.detail:
                    btn_id = f"btn-detail-{check_id}"
                    self._fail_details[btn_id] = (label_text, result.detail)
                    await row.mount(Button(
                        "View Details",
                        id=btn_id,
                        variant="error",
                        classes="info-row-fail-btn",
                    ))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "btn-configure":
            from .config_editor import ConfigEditorScreen
            self.app.push_screen(ConfigEditorScreen(self._config))
        elif btn_id == "btn-start":
            from .phase1 import Phase1Screen
            self.app.push_screen(Phase1Screen(self._config))
        elif btn_id and btn_id in self._fail_details:
            title, detail = self._fail_details[btn_id]
            self.app.push_screen(DetailModal(title, detail))


def _config_row(label: str, value: str) -> Horizontal:
    row = Horizontal(classes="config-row")
    row.compose_add_child(Label(label))
    row.compose_add_child(Label(value))
    return row
