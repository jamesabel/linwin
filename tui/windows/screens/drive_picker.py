"""Drive picker modal — scan and select the best drive for WSL storage."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static
from textual import work

from ...shared.widgets import AsciiRadioSet
from ..tasks.drive_scan import DriveScanResult, scan_drives


class DrivePickerModal(ModalScreen[str | None]):
    """Modal that scans drives and lets the user pick one."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
    ]

    CSS = """
    DrivePickerModal {
        align: center middle;
    }
    #picker-dialog {
        width: 90;
        max-width: 95%;
        height: auto;
        max-height: 80%;
        border: ascii $primary;
        background: $surface;
        padding: 1 2;
    }
    #picker-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #picker-status {
        margin: 1 0;
    }
    #picker-excluded {
        color: $text-muted;
        margin-top: 1;
    }
    #picker-hint {
        margin-top: 1;
        text-align: center;
        color: $text-muted;
    }
    #drive-radio-set {
        height: auto;
        max-height: 15;
    }
    """

    def __init__(self, current_letter: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_letter = current_letter.upper()
        self._scan_result: DriveScanResult | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-dialog"):
            yield Static("Select Drive for WSL Storage", id="picker-title")
            yield Static("Scanning drives...", id="picker-status")

    def on_mount(self) -> None:
        self._run_scan()

    @work(exclusive=True)
    async def _run_scan(self) -> None:
        result = await scan_drives()
        self._scan_result = result
        dialog = self.query_one("#picker-dialog")
        status = self.query_one("#picker-status", Static)

        if result.error:
            status.update(f"[red]{result.error}[/]")
            await dialog.mount(Static("Press Escape to close", id="picker-hint"))
            return

        if not result.candidates:
            status.update("[red]No suitable drives found.[/]")
            if result.excluded:
                lines = ["Excluded drives:"]
                for letter, reason in result.excluded:
                    lines.append(f"  {letter}: - {reason}")
                await dialog.mount(Static("\n".join(lines), id="picker-excluded"))
            await dialog.mount(Static("Press Escape to close", id="picker-hint"))
            return

        status.update("Select a drive (ranked by performance and free space):")

        # Build radio options
        labels = []
        for i, drive in enumerate(result.candidates):
            recommended = " (recommended)" if i == 0 else ""
            current = " (current)" if drive.letter.upper() == self._current_letter else ""
            label = (
                f"{drive.letter}: - {drive.type_display}, "
                f"{drive.free_gb} GB free / {drive.total_gb} GB total"
            )
            if drive.label:
                label += f' "{drive.label}"'
            label += f"{recommended}{current}"
            labels.append(label)

        radio_set = AsciiRadioSet(labels, default=0, id="drive-radio-set")
        await dialog.mount(radio_set)

        if result.excluded:
            lines = ["Excluded:"]
            for letter, reason in result.excluded:
                lines.append(f"  {letter}: - {reason}")
            await dialog.mount(Static("\n".join(lines), id="picker-excluded"))

        await dialog.mount(
            Static("Press Enter to select, Escape to cancel", id="picker-hint")
        )

        self._bind_enter()

    def _bind_enter(self) -> None:
        """Add Enter binding after scan completes and options are available."""
        self._bindings.bind("enter", "select", "Select", show=True)

    def action_select(self) -> None:
        if not self._scan_result or not self._scan_result.candidates:
            return
        try:
            radio_set = self.query_one("#drive-radio-set", AsciiRadioSet)
            idx = radio_set.pressed_index
            if idx >= 0:
                self.dismiss(self._scan_result.candidates[idx].letter)
        except Exception:
            pass

    def action_cancel(self) -> None:
        self.dismiss(None)
