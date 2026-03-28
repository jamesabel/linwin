"""Windows TUI Configuration Editor Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from ...shared.config import SetupConfig, SnapPackage, save_config
from ...shared.widgets import AsciiCheckbox


class ConfigEditorScreen(Screen):
    """Edit config.json values interactively."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    .editor-section {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    .editor-section .section-header {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    .field-row {
        height: 1;
        layout: horizontal;
    }
    .field-row Label {
        width: 20;
        text-style: bold;
    }
    .field-row Input {
        width: 1fr;
    }
    .snap-row {
        height: 3;
        layout: horizontal;
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
    #btn-save {
        color: $success;
    }
    #btn-scan-drives {
        color: $warning;
    }
    """

    # Known snap packages for checkboxes
    AVAILABLE_SNAPS = [
        ("code", "VS Code"),
        ("intellij-idea-community", "IntelliJ IDEA Community"),
        ("pycharm-community", "PyCharm Community"),
    ]

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        c = self._config
        wc = c.wslconfig
        with VerticalScroll():
            with Vertical(classes="editor-section"):
                yield Static("WSL Settings", classes="section-header")
                yield _field("Distro Name:", c.distroName, "input-distro-name")
                yield _field("Import Name:", c.distroImportName, "input-import-name")
                yield _field("Drive Letter:", c.wslDriveLetter, "input-drive-letter")
                yield Static(">> Scan Drives <<", id="btn-scan-drives", classes="action-link")
                yield _field("Install Path:", c.wslInstallPath, "input-install-path")

            with Vertical(classes="editor-section"):
                yield Static("Resource Limits", classes="section-header")
                yield _field("Memory:", wc.memory, "input-memory")
                yield _field("Processors:", str(wc.processors), "input-processors")
                yield _field("Swap:", wc.swap, "input-swap")
                yield _field("VHD Size:", wc.defaultVhdSize, "input-vhd-size")

            with Vertical(classes="editor-section"):
                yield Static("IDE Selection (Snaps)", classes="section-header")
                selected = {s.name for s in c.snaps}
                for snap_id, snap_label in self.AVAILABLE_SNAPS:
                    yield AsciiCheckbox(snap_label, value=snap_id in selected, id=f"snap-{snap_id}")

            with Vertical(classes="editor-section"):
                yield Static("Apt Packages", classes="section-header")
                yield _field("Packages:", ", ".join(c.aptPackages), "input-apt-packages")

            with Horizontal(classes="button-bar"):
                yield Static(">> Save & Back <<", id="btn-save", classes="action-link")
                yield Static(">> Cancel <<", id="btn-cancel", classes="action-link")

    def action_cancel(self) -> None:
        self.app.pop_screen()

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if not widget_id:
            return
        if widget_id == "btn-save":
            self._save_config()
            self.app.pop_screen()
        elif widget_id == "btn-cancel":
            self.app.pop_screen()
        elif widget_id == "btn-scan-drives":
            from .drive_picker import DrivePickerModal
            current = self.query_one("#input-drive-letter", Input).value
            self.app.push_screen(DrivePickerModal(current), self._on_drive_selected)

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

        # Snaps
        snaps = []
        for snap_id, _ in self.AVAILABLE_SNAPS:
            cb = self.query_one(f"#snap-{snap_id}", AsciiCheckbox)
            if cb.value:
                snaps.append(SnapPackage(snap_id, True))
        c.snaps = snaps

        # Apt packages
        apt_str = self.query_one("#input-apt-packages", Input).value
        c.aptPackages = [p.strip() for p in apt_str.split(",") if p.strip()]

        save_config(c)


def _field(label: str, value: str, input_id: str) -> Horizontal:
    row = Horizontal(classes="field-row")
    row.compose_add_child(Label(label))
    row.compose_add_child(Input(value=value, id=input_id))
    return row
