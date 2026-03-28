"""Windows TUI Phase 1 Screen — enable features and reboot prompt."""

from __future__ import annotations

import asyncio

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.widgets import LogPanel, TaskListWidget
from ..tasks import features, validators
from ..tasks.state import SetupState, save_state


PHASE1_TASKS = [
    ("validate_build", "Validate Windows build"),
    ("check_virt", "Check virtualization"),
    ("check_drive", "Check target drive"),
    ("check_wsl", "Check WSL feature"),
    ("enable_wsl", "Enable WSL feature"),
    ("check_vm", "Check VM Platform feature"),
    ("enable_vm", "Enable VM Platform feature"),
]


class Phase1Screen(Screen):
    """Phase 1: Enable Windows features, then prompt for reboot."""

    CSS = """
    #phase1-status {
        padding: 1 2;
        text-style: bold;
        color: $text;
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
    .hidden {
        display: none;
    }
    #btn-phase2 {
        color: $success;
    }
    #btn-reboot {
        color: $warning;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._needs_reboot = False

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield TaskListWidget(PHASE1_TASKS, id="phase1-tasks")
            yield LogPanel(id="phase1-log")
            yield Static("", id="phase1-status")
            with Horizontal(classes="button-bar", id="phase1-buttons"):
                yield Static(">> Continue to Phase 2 <<", id="btn-phase2", classes="action-link hidden")
                yield Static(">> Reboot Now <<", id="btn-reboot", classes="action-link hidden")

    def on_mount(self) -> None:
        self.run_phase1()

    @work(exclusive=True)
    async def run_phase1(self) -> None:
        tasks = self.query_one("#phase1-tasks", TaskListWidget)
        log = self.query_one("#phase1-log", LogPanel)
        status = self.query_one("#phase1-status", Static)

        async def on_line(line: str, stream: str) -> None:
            if stream == "stderr":
                log.write_stderr(line)
            else:
                log.write_stdout(line)

        # 1. Validate Windows build
        tasks.set_status("validate_build", "running")
        log.write_command("Checking Windows build...")
        result = await validators.check_windows_build(on_line)
        tasks.set_status("validate_build", "done" if result.ok else "failed")
        if not result.ok:
            log.write_error(f"FAILED: {result.message}")
            status.update("[red]Setup cannot continue. Windows build too old.[/]")
            return

        # 2. Check virtualization
        tasks.set_status("check_virt", "running")
        log.write_command("Checking virtualization...")
        result = await validators.check_virtualization(on_line)
        tasks.set_status("check_virt", "done" if result.ok else "failed")
        if not result.ok:
            log.write_error(f"FAILED: {result.message}")
            if result.detail:
                for detail_line in result.detail.splitlines():
                    log.write_error(detail_line)
            status.update("[red]Enable virtualization in BIOS/UEFI and try again.[/]")
            return

        # 3. Check drive
        tasks.set_status("check_drive", "running")
        log.write_command(f"Checking drive {self._config.wslDriveLetter}:...")
        result = await validators.check_drive_exists(self._config.wslDriveLetter, on_line)
        tasks.set_status("check_drive", "done" if result.ok else "failed")
        if not result.ok:
            log.write_error(f"FAILED: {result.message}")
            status.update(f"[red]Drive {self._config.wslDriveLetter}: not found.[/]")
            return

        # 4. Check WSL feature
        tasks.set_status("check_wsl", "running")
        log.write_command("Checking WSL feature...")
        wsl_enabled = await features.check_feature("Microsoft-Windows-Subsystem-Linux", on_line)
        tasks.set_status("check_wsl", "done" if wsl_enabled else "skipped")

        # 5. Enable WSL feature if needed
        if wsl_enabled:
            tasks.set_status("enable_wsl", "skipped")
            log.write_info("WSL feature already enabled.")
        else:
            tasks.set_status("enable_wsl", "running")
            log.write_command("Enabling WSL feature via DISM...")
            fr = await features.enable_wsl_feature(on_line)
            tasks.set_status("enable_wsl", "done" if fr.ok else "failed")
            if not fr.ok:
                log.write_error(f"FAILED: {fr.error}")
                status.update("[red]Failed to enable WSL feature.[/]")
                return
            self._needs_reboot = True

        # 6. Check VM Platform feature
        tasks.set_status("check_vm", "running")
        log.write_command("Checking Virtual Machine Platform...")
        vm_enabled = await features.check_feature("VirtualMachinePlatform", on_line)
        tasks.set_status("check_vm", "done" if vm_enabled else "skipped")

        # 7. Enable VM Platform if needed
        if vm_enabled:
            tasks.set_status("enable_vm", "skipped")
            log.write_info("Virtual Machine Platform already enabled.")
        else:
            tasks.set_status("enable_vm", "running")
            log.write_command("Enabling Virtual Machine Platform via DISM...")
            fr = await features.enable_vm_platform(on_line)
            tasks.set_status("enable_vm", "done" if fr.ok else "failed")
            if not fr.ok:
                log.write_error(f"FAILED: {fr.error}")
                status.update("[red]Failed to enable Virtual Machine Platform.[/]")
                return
            self._needs_reboot = True

        # Done — show appropriate buttons
        if self._needs_reboot:
            log.write_success("Features enabled. A reboot is required.")
            status.update("[yellow]Reboot required. After reboot, re-run this TUI to continue at Phase 2.[/]")
            self.query_one("#btn-reboot").remove_class("hidden")

            # Save state for post-reboot resume
            save_state(SetupState(
                phase1_complete=True,
                needs_reboot=True,
                config_path=str(self._config.wslInstallPath),
            ))
        else:
            log.write_success("All features already enabled. No reboot needed.")
            status.update("[green]Phase 1 complete. Ready for Phase 2.[/]")
            self.query_one("#btn-phase2").remove_class("hidden")

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if not widget_id:
            return
        if widget_id == "btn-phase2":
            from .phase2 import Phase2Screen
            self.app.switch_screen(Phase2Screen(self._config))
        elif widget_id == "btn-reboot":
            import subprocess
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
            self.app.exit()
