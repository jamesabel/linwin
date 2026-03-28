"""Linux TUI Configuration Editor Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from ...shared.config import SetupConfig, SnapPackage, save_config
from ...shared.widgets import AsciiCheckbox


class ConfigEditorScreen(Screen):
    """Edit Linux-relevant config.json values."""

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
    .section-header {
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
    """

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
        with VerticalScroll():
            with Vertical(classes="editor-section"):
                yield Static("IDE Selection (Snaps)", classes="section-header")
                selected = {s.name for s in c.snaps}
                for snap_id, snap_label in self.AVAILABLE_SNAPS:
                    yield AsciiCheckbox(snap_label, value=snap_id in selected, id=f"snap-{snap_id}")

            with Vertical(classes="editor-section"):
                yield Static("Apt Packages", classes="section-header")
                yield _field("Packages:", ", ".join(c.aptPackages), "input-apt-packages")

            with Vertical(classes="editor-section"):
                yield Static("Options", classes="section-header")
                yield AsciiCheckbox("Enable Systemd", value=c.enableSystemd, id="chk-systemd")

            with Vertical(classes="button-bar"):
                yield Static(">> Save & Back <<", id="btn-save", classes="action-link")
                yield Static(">> Cancel (Escape) <<", id="btn-cancel", classes="action-link")

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

    def _save_config(self) -> None:
        c = self._config

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

        # Systemd
        c.enableSystemd = self.query_one("#chk-systemd", AsciiCheckbox).value

        save_config(c)


def _field(label: str, value: str, input_id: str) -> Horizontal:
    row = Horizontal(classes="field-row")
    row.compose_add_child(Label(label))
    row.compose_add_child(Input(value=value, id=input_id))
    return row
