"""Linux TUI Configuration Editor Screen."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input, Static

from ...shared.base_app import ClickDispatchScreen
from ...shared.config import APP_REGISTRY, SetupConfig, collect_app_selections, parse_apt_input, save_config
from ...shared.widgets import AsciiCheckbox, field_row


class ConfigEditorScreen(ClickDispatchScreen):
    """Edit Linux-relevant config.json values."""

    BINDINGS = [
        ("1", "save", "Save"),
        ("escape", "cancel", "Cancel"),
    ]

    CLICK_MAP = {
        "btn-save": "save",
        "btn-cancel": "cancel",
    }

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
                yield Static("Optional Applications", classes="section-header")
                selected_ids = {a.id for a in c.optionalApps}
                for app in APP_REGISTRY:
                    suffix = f" ({app.install_method})" if app.install_method != "snap" else ""
                    if app.install_method == "custom":
                        suffix = " (custom — install separately)"
                    yield AsciiCheckbox(
                        f"{app.display_name}{suffix}",
                        value=app.id in selected_ids,
                        id=f"app-{app.id}",
                    )

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

    def _save_config(self) -> None:
        c = self._config

        from ...shared.config import SnapPackage
        c.optionalApps = collect_app_selections(self.query_one)
        c.snaps = [SnapPackage(a.id, a.classic) for a in c.optionalApps if a.install_method == "snap"]
        c.aptPackages = parse_apt_input(self.query_one("#input-apt-packages", Input).value)

        # Systemd
        c.enableSystemd = self.query_one("#chk-systemd", AsciiCheckbox).value

        save_config(c)


