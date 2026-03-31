"""Setup Proposal Screen — shows auto-detected config for user approval."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static

from ...shared.config import SetupConfig, save_config
from ...shared.widgets import info_row
from ..tasks.auto_config import SystemProfile
from ..tasks.full_verify import VerifyResult


class SetupProposalScreen(Screen):
    """Shows verification failures, detected system info, and proposed config."""

    BINDINGS = [
        ("1", "accept", "Accept"),
        ("2", "edit", "Edit"),
        ("3", "cancel", "Cancel"),
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    #proposal-title {
        text-style: bold;
        color: $warning;
        padding: 1 2;
        text-align: center;
    }
    .proposal-section {
        border: ascii $primary;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    .proposal-section-warn {
        border: ascii $warning;
        padding: 1 2;
        margin: 1 2;
        height: auto;
    }
    #btn-accept {
        color: $success;
    }
    #btn-edit {
        color: $accent;
    }
    #btn-cancel {
        color: $text;
    }
    """

    def __init__(
        self,
        config: SetupConfig,
        profile: SystemProfile,
        verify_result: VerifyResult,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._profile = profile
        self._verify_result = verify_result

    def compose(self) -> ComposeResult:
        config = self._config
        profile = self._profile

        with VerticalScroll():
            yield Static("Setup Required", id="proposal-title")

            # --- Failed checks ---
            failed = self._verify_result.failed_checks
            if failed:
                with Vertical(classes="proposal-section-warn"):
                    yield Static("Issues Detected", classes="section-header")
                    for item in failed:
                        yield Static(f"  [red]FAIL[/]  {item.name}")

            # --- System info ---
            with Vertical(classes="proposal-section"):
                yield Static("Detected System", classes="section-header")
                yield info_row("RAM:", f"{profile.ram_gb} GB")
                yield info_row("CPUs:", f"{profile.cpu_count} logical processors")
                if profile.best_drive:
                    d = profile.best_drive
                    yield info_row("Best Drive:", f"{d.letter}: ({d.type_display}, {d.free_gb:.0f} GB free)")
                else:
                    yield info_row("Best Drive:", "None found (will use C:)")

            # --- Proposed config ---
            with Vertical(classes="proposal-section"):
                yield Static("Proposed Configuration", classes="section-header")
                yield info_row("WSL Memory:", f"{config.wslconfig.memory} (1/4 of {profile.ram_gb} GB)")
                yield info_row("WSL Processors:", f"{config.wslconfig.processors} (half of {profile.cpu_count})")
                yield info_row("WSL Drive:", f"{config.wslDriveLetter}:")
                yield info_row("Install Path:", config.wslInstallPath)
                yield info_row("VHD Size:", f"{config.wslconfig.defaultVhdSize} (sparse)")
                yield info_row("Swap:", config.wslconfig.swap)
                yield info_row("Distro:", config.distroName)
                snap_text = ", ".join(s.name for s in config.snaps) if config.snaps else "None (install later from launcher)"
                yield info_row("Snaps:", snap_text)
                yield info_row("Apt Packages:", ", ".join(config.aptPackages))

            # --- Buttons ---
            with Vertical(classes="button-bar"):
                yield Static("\\[1] Accept & Run Setup", id="btn-accept", classes="action-link")
                yield Static("\\[2] Edit Configuration", id="btn-edit", classes="action-link")
                yield Static("\\[3] Cancel", id="btn-cancel", classes="action-link")

    def on_click(self, event) -> None:
        widget_id = getattr(event.widget, "id", None)
        if widget_id == "btn-accept":
            save_config(self._config)
            from .setup import SetupScreen
            self.app.switch_screen(SetupScreen(self._config))
        elif widget_id == "btn-edit":
            from .config_editor import ConfigEditorScreen
            self.app.push_screen(ConfigEditorScreen(self._config), callback=self._on_editor_close)
        elif widget_id == "btn-cancel":
            self.app.exit()

    def action_accept(self) -> None:
        save_config(self._config)
        from .setup import SetupScreen
        self.app.switch_screen(SetupScreen(self._config))

    def action_edit(self) -> None:
        from .config_editor import ConfigEditorScreen
        self.app.push_screen(ConfigEditorScreen(self._config), callback=self._on_editor_close)

    def action_cancel(self) -> None:
        self.app.exit()

    def _on_editor_close(self, _result=None) -> None:
        """Refresh after config editor closes."""
        # Rebuild the screen with potentially updated config
        from ...shared.config import load_config
        try:
            self._config = load_config()
        except FileNotFoundError:
            pass
        # Remount to refresh the display
        self.app.switch_screen(
            SetupProposalScreen(self._config, self._profile, self._verify_result)
        )
