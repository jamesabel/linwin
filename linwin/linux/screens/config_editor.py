"""Linux TUI Configuration Editor Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Label, Static

from ...shared.config import AVAILABLE_SNAPS, SetupConfig, SnapPackage, save_config
from ...shared.widgets import AsciiCheckbox, field_row


class ConfigEditorScreen(Screen):
    """Edit Linux-relevant config.json values."""

    BINDINGS = [
        ("1", "save", "Save"),
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    .editor-section {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    #btn-save {
        color: $success;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        c = self._config
        with VerticalScroll():
            with Vertical(classes="editor-section"):
                yield Static("IDE Selection (Snaps)", classes="section-header")
                selected = {s.name for s in c.snaps}
                for snap_id, snap_label in AVAILABLE_SNAPS:
                    yield AsciiCheckbox(snap_label, value=snap_id in selected, id=f"snap-{snap_id}")

            with Vertical(classes="editor-section"):
                yield Static("Apt Packages", classes="section-header")
                yield field_row("Packages:", ", ".join(c.aptPackages), "input-apt-packages")

            with Vertical(classes="editor-section"):
                yield Static("Options", classes="section-header")
                yield AsciiCheckbox("Enable Systemd", value=c.enableSystemd, id="chk-systemd")

            with Vertical(classes="button-bar"):
                yield Static("\\[1] Save & Back", id="btn-save", classes="action-link")
                yield Static("\\[Esc] Cancel", id="btn-cancel", classes="action-link")

    def action_save(self) -> None:
        self._save_config()
        self.app.pop_screen()

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
        for snap_id, _ in AVAILABLE_SNAPS:
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


