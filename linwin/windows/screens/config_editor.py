"""Windows TUI Configuration Editor Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Static

from ...shared.base_app import ClickDispatchScreen
from ...shared.config import AVAILABLE_SNAPS, SetupConfig, collect_snap_selections, parse_apt_input, save_config
from ...shared.widgets import AsciiCheckbox, field_row


class ConfigEditorScreen(ClickDispatchScreen):
    """Edit config.json values interactively."""

    BINDINGS = [
        ("1", "save", "Save"),
        ("2", "scan_drives", "Scan Drives"),
        ("escape", "cancel", "Cancel"),
    ]

    CLICK_MAP = {
        "btn-save": "save",
        "btn-cancel": "cancel",
        "btn-scan-drives": "scan_drives",
    }

    CSS = """
    .editor-section {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    .snap-row {
        height: 3;
        layout: horizontal;
    }
    #btn-save {
        color: $success;
    }
    #btn-scan-drives {
        color: $warning;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        c = self._config
        wc = c.wslconfig
        with VerticalScroll():
            with Vertical(classes="editor-section"):
                yield Static("WSL Settings", classes="section-header")
                yield field_row("Distro Name:", c.distroName, "input-distro-name")
                yield field_row("Import Name:", c.distroImportName, "input-import-name")
                yield field_row("Drive Letter:", c.wslDriveLetter, "input-drive-letter")
                yield Static("\\[2] Scan Drives", id="btn-scan-drives", classes="action-link")
                yield field_row("Install Path:", c.wslInstallPath, "input-install-path")

            with Vertical(classes="editor-section"):
                yield Static("Resource Limits", classes="section-header")
                yield field_row("Memory:", wc.memory, "input-memory")
                yield field_row("Processors:", str(wc.processors), "input-processors")
                yield field_row("Swap:", wc.swap, "input-swap")
                yield field_row("VHD Size:", wc.defaultVhdSize, "input-vhd-size")

            with Vertical(classes="editor-section"):
                yield Static("IDE Selection (Snaps)", classes="section-header")
                selected = {s.name for s in c.snaps}
                for snap_id, snap_label in AVAILABLE_SNAPS:
                    yield AsciiCheckbox(snap_label, value=snap_id in selected, id=f"snap-{snap_id}")

            with Vertical(classes="editor-section"):
                yield Static("Apt Packages", classes="section-header")
                yield field_row("Packages:", ", ".join(c.aptPackages), "input-apt-packages")

            with Vertical(classes="button-bar"):
                yield Static("\\[1] Save & Back", id="btn-save", classes="action-link")
                yield Static("\\[Esc] Cancel", id="btn-cancel", classes="action-link")

    def action_save(self) -> None:
        self._save_config()
        self.app.pop_screen()

    def action_scan_drives(self) -> None:
        from .drive_picker import DrivePickerModal
        current = self.query_one("#input-drive-letter", Input).value
        self.app.push_screen(DrivePickerModal(current), self._on_drive_selected)

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def _on_drive_selected(self, letter: str | None) -> None:
        if letter:
            self.query_one("#input-drive-letter", Input).value = letter
            # Update install path to match
            path_input = self.query_one("#input-install-path", Input)
            path_input.value = f"{letter}:\\WSL\\{self._config.distroImportName}"

    def _save_config(self) -> None:
        c = self._config
        wc = c.wslconfig

        c.distroName = self.query_one("#input-distro-name", Input).value
        c.distroImportName = self.query_one("#input-import-name", Input).value
        c.wslDriveLetter = self.query_one("#input-drive-letter", Input).value
        c.wslInstallPath = self.query_one("#input-install-path", Input).value

        wc.memory = self.query_one("#input-memory", Input).value
        try:
            wc.processors = int(self.query_one("#input-processors", Input).value)
        except ValueError:
            pass
        wc.swap = self.query_one("#input-swap", Input).value
        wc.defaultVhdSize = self.query_one("#input-vhd-size", Input).value

        c.snaps = collect_snap_selections(self.query_one)
        c.aptPackages = parse_apt_input(self.query_one("#input-apt-packages", Input).value)

        save_config(c)


