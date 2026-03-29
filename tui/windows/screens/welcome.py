"""Windows TUI Welcome Screen — system info and config summary."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Label, Static
from textual import work

from ...shared.config import SetupConfig
from ..tasks import validators


class DetailModal(ModalScreen):
    """Modal that shows the detail text for a failed check."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    CSS = """
    DetailModal {
        align: center middle;
    }
    #detail-dialog {
        width: 80;
        max-width: 90%;
        height: auto;
        max-height: 80%;
        border: ascii $error;
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
        text-align: center;
        color: $text;
        text-style: bold;
        margin-top: 1;
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
            yield Static("Press Escape or q to close", id="detail-close")

    def action_close(self) -> None:
        self.dismiss()


class WelcomeScreen(Screen):
    """Welcome screen with system detection and config summary."""

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
    #detecting-label {
        margin: 1 3;
        color: $warning;
    }
    .detail-link {
        width: 1fr;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._fail_details: dict[str, tuple[str, str]] = {}  # button_id -> (title, detail)

    def compose(self) -> ComposeResult:
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
                if result.detail:
                    link_id = f"detail-link-{check_id}"
                    self._fail_details[link_id] = (label_text, result.detail)
                    link = Static(
                        f"{result.message}  [red]FAIL[/] - [bold yellow]Click here for instructions[/]",
                        id=link_id,
                        classes="detail-link",
                    )
                    await row.mount(link)
                else:
                    await row.mount(Label(f"{result.message}  [red]FAIL[/]"))

    def on_click(self, event) -> None:
        """Handle clicks on action links and detail links."""
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
        elif widget_id in self._fail_details:
            title, detail = self._fail_details[widget_id]
            self.app.push_screen(DetailModal(title, detail))


def _config_row(label: str, value: str) -> Horizontal:
    row = Horizontal(classes="config-row")
    row.compose_add_child(Label(label))
    row.compose_add_child(Label(value))
    return row
