"""Windows TUI Setup Screen — single unified flow for all setup tasks."""

from __future__ import annotations

import asyncio
import os

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig, windows_to_wsl_path
from ...shared.setup_logging import get_logger
from ...shared.widgets import LogPanel, TaskListWidget
from ..tasks import features, validators, wsl_install
from ..tasks.linux_invoke import run_linux_headless
from ..tasks.state import SetupState, clear_state, save_state
from ..tasks.wsl_config import write_wslconfig


SETUP_TASKS = [
    # Feature checks / enables (may require reboot)
    ("validate_build", "Validate Windows build"),
    ("check_virt", "Check virtualization"),
    ("check_drive", "Check target drive"),
    ("check_wsl", "Check WSL feature"),
    ("enable_wsl", "Enable WSL feature"),
    ("check_vm", "Check VM Platform feature"),
    ("enable_vm", "Enable VM Platform feature"),
    # WSL install + Linux setup (post-reboot if needed)
    ("update_wsl", "Update WSL"),
    ("set_version", "Set WSL default version 2"),
    ("install_distro", "Install Ubuntu"),
    ("export_distro", "Export distro"),
    ("import_distro", "Import distro to target drive"),
    ("set_user", "Set default user"),
    ("write_config", "Write .wslconfig"),
    ("shutdown_wsl", "Shutdown WSL"),
    ("linux_systemd", "Linux setup: enable systemd"),
    ("restart_wsl", "Restart WSL"),
    ("linux_packages", "Linux setup: install packages"),
    ("linux_xrdp", "Linux setup: install and configure xrdp"),
]

RESUME_AFTER_REBOOT = "update_wsl"


class SetupScreen(Screen):
    """Single setup screen that runs all tasks, pausing for reboot only when needed."""

    CSS = """
    #setup-status {
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
    #btn-verify {
        color: $success;
    }
    #btn-reboot {
        color: $warning;
    }
    #btn-launcher {
        color: $accent;
    }
    """

    def __init__(self, config: SetupConfig, resume_from: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._resume_from = resume_from
        self._needs_reboot = False

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield TaskListWidget(SETUP_TASKS, id="setup-tasks")
            yield LogPanel(id="setup-log")
            yield Static("", id="setup-status")
            with Horizontal(classes="button-bar"):
                yield Static(">> Reboot Now <<", id="btn-reboot", classes="action-link hidden")
                yield Static(">> Run Verification <<", id="btn-verify", classes="action-link hidden")
                yield Static(">> Go to Launcher <<", id="btn-launcher", classes="action-link hidden")

    def on_mount(self) -> None:
        self.run_setup()

    @work(exclusive=True)
    async def run_setup(self) -> None:
        flog = get_logger()
        flog.info("=== Setup started ===")
        tasks = self.query_one("#setup-tasks", TaskListWidget)
        log = self.query_one("#setup-log", LogPanel)
        status = self.query_one("#setup-status", Static)
        config = self._config

        # Determine resume point
        task_ids = [t[0] for t in SETUP_TASKS]
        if self._resume_from and self._resume_from in task_ids:
            start_index = task_ids.index(self._resume_from)
            for i in range(start_index):
                tasks.set_status(task_ids[i], "done")
            log.write_info("Resuming after reboot...")
            flog.info("Resuming from task %s (index %d)", self._resume_from, start_index)
        else:
            start_index = 0

        async def on_line(line: str, stream: str) -> None:
            if stream == "stderr":
                log.write_stderr(line)
            else:
                log.write_stdout(line)

        # Helper for simple task execution
        async def run_task(task_id: str, coro, fail_msg: str = "") -> bool:
            tasks.set_status(task_id, "running")
            result = await coro
            if hasattr(result, "ok"):
                ok = result.ok
                msg = getattr(result, "message", "")
                skipped = getattr(result, "skipped", False)
            elif isinstance(result, bool):
                ok = result
                msg = ""
                skipped = False
            else:
                ok = True
                msg = ""
                skipped = False

            if skipped:
                tasks.set_status(task_id, "skipped")
                log.write_info(f"Skipped: {msg}")
            elif ok:
                tasks.set_status(task_id, "done")
                if msg:
                    log.write_success(msg)
            else:
                tasks.set_status(task_id, "failed")
                log.write_error(fail_msg or msg)
                return False
            return True

        # ── Feature checks / enables ─────────────────────────────

        if start_index <= task_ids.index("validate_build"):
            tasks.set_status("validate_build", "running")
            log.write_command("Checking Windows build...")
            result = await validators.check_windows_build(on_line)
            tasks.set_status("validate_build", "done" if result.ok else "failed")
            if not result.ok:
                log.write_error(f"FAILED: {result.message}")
                status.update("[red]Setup cannot continue. Windows build too old.[/]")
                return

        if start_index <= task_ids.index("check_virt"):
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

        if start_index <= task_ids.index("check_drive"):
            tasks.set_status("check_drive", "running")
            log.write_command(f"Checking drive {config.wslDriveLetter}:...")
            result = await validators.check_drive_exists(config.wslDriveLetter, on_line)
            tasks.set_status("check_drive", "done" if result.ok else "failed")
            if not result.ok:
                log.write_error(f"FAILED: {result.message}")
                status.update(f"[red]Drive {config.wslDriveLetter}: not found.[/]")
                return

        if start_index <= task_ids.index("check_wsl"):
            tasks.set_status("check_wsl", "running")
            log.write_command("Checking WSL feature...")
            wsl_enabled = await features.check_feature("Microsoft-Windows-Subsystem-Linux", on_line)
            tasks.set_status("check_wsl", "done" if wsl_enabled else "skipped")

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

        if start_index <= task_ids.index("check_vm"):
            tasks.set_status("check_vm", "running")
            log.write_command("Checking Virtual Machine Platform...")
            vm_enabled = await features.check_feature("VirtualMachinePlatform", on_line)
            tasks.set_status("check_vm", "done" if vm_enabled else "skipped")

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

        # ── Reboot checkpoint ────────────────────────────────────

        if self._needs_reboot:
            flog.info("=== Reboot required, saving state ===")
            log.write_success("Features enabled. A reboot is required.")
            status.update("[yellow]Reboot required. After reboot, re-run to continue setup.[/]")
            self.query_one("#btn-reboot").remove_class("hidden")
            save_state(SetupState(
                resume_from_task=RESUME_AFTER_REBOOT,
                config_path=str(config.wslInstallPath),
            ))
            return

        # ── WSL install + Linux setup ────────────────────────────

        # Update WSL
        if start_index <= task_ids.index("update_wsl"):
            log.write_command("wsl --update")
            if not await run_task("update_wsl", wsl_install.update_wsl(on_line), "WSL update failed"):
                status.update("[red]WSL update failed.[/]")
                return

        # Set default version
        if start_index <= task_ids.index("set_version"):
            log.write_command("wsl --set-default-version 2")
            if not await run_task("set_version", wsl_install.set_wsl_default_version(on_line)):
                status.update("[red]Failed to set WSL version.[/]")
                return

        # Install distro
        if start_index <= task_ids.index("install_distro"):
            log.write_command(f"Installing {config.distroName}...")
            if not await run_task("install_distro", wsl_install.install_distro(config, on_line)):
                status.update("[red]Failed to install distro.[/]")
                return

        # Export distro
        if start_index <= task_ids.index("export_distro"):
            log.write_command("Exporting distro...")
            tasks.set_status("export_distro", "running")
            export_result, tar_path = await wsl_install.export_distro(config, on_line)
            if export_result.skipped:
                tasks.set_status("export_distro", "skipped")
                tasks.set_status("import_distro", "skipped")
                log.write_info("Distro already on target drive.")
            elif export_result.ok:
                tasks.set_status("export_distro", "done")
                log.write_success(export_result.message)

                # Import distro
                log.write_command(f"Importing distro to {config.wslInstallPath}...")
                if not await run_task("import_distro", wsl_install.import_distro(config, tar_path, on_line)):
                    status.update("[red]Failed to import distro.[/]")
                    return
            else:
                tasks.set_status("export_distro", "failed")
                log.write_error(export_result.message)
                status.update("[red]Failed to export distro.[/]")
                return

        # Set default user
        if start_index <= task_ids.index("set_user"):
            log.write_command("Detecting and setting default user...")
            tasks.set_status("set_user", "running")
            username = await wsl_install.detect_default_user(config, on_line)
            if username:
                log.write_info(f"Detected user: {username}")
                user_result = await wsl_install.set_default_user(config, username, on_line)
                if user_result.skipped:
                    tasks.set_status("set_user", "skipped")
                elif user_result.ok:
                    tasks.set_status("set_user", "done")
                else:
                    tasks.set_status("set_user", "failed")
                    log.write_error(user_result.message)
            else:
                tasks.set_status("set_user", "skipped")
                log.write_info("No user found in /home/. Default user will be root.")

        # Write .wslconfig
        if start_index <= task_ids.index("write_config"):
            log.write_command("Writing .wslconfig...")
            tasks.set_status("write_config", "running")
            wc_result = write_wslconfig(config, overwrite=True)
            if wc_result.ok:
                tasks.set_status("write_config", "done")
                log.write_success(wc_result.message)
            else:
                log.write_info("Overwriting existing .wslconfig...")
                wc_result = write_wslconfig(config, overwrite=True)
                tasks.set_status("write_config", "done" if wc_result.ok else "failed")

        # Shutdown WSL
        if start_index <= task_ids.index("shutdown_wsl"):
            log.write_command("wsl --shutdown")
            await run_task("shutdown_wsl", wsl_install.shutdown_wsl(on_line))
            await asyncio.sleep(3)

        # Compute script dir for Linux invocation
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        async def on_task_update(task_id: str, task_status: str) -> None:
            log.write_info(f"  [{task_id}] {task_status}")

        # Linux: enable systemd
        if start_index <= task_ids.index("linux_systemd"):
            log.write_command("Running Linux setup: enable systemd...")
            tasks.set_status("linux_systemd", "running")
            lp1 = await run_linux_headless(config, "enable-systemd", script_dir, on_line, on_task_update)
            tasks.set_status("linux_systemd", "done" if lp1.success else "failed")
            if not lp1.success:
                log.write_error("Linux enable-systemd failed")
                status.update("[red]Linux setup: enable systemd failed.[/]")
                return

        # Restart WSL (for systemd)
        if start_index <= task_ids.index("restart_wsl"):
            log.write_command("Restarting WSL for systemd...")
            await run_task("restart_wsl", wsl_install.shutdown_wsl(on_line))

            # Wait for WSL to be fully ready
            log.write_info("Waiting for WSL to become ready...")
            flog.info("Probing WSL readiness after restart...")
            ready = await wsl_install.wait_for_wsl_ready(config, on_line)
            if not ready:
                flog.warning("WSL readiness probe timed out, proceeding anyway")
                log.write_info("WSL slow to respond, proceeding...")

        # Linux: install packages (with retry)
        if start_index <= task_ids.index("linux_packages"):
            log.write_command("Running Linux setup: install packages...")
            tasks.set_status("linux_packages", "running")
            max_retries = 2
            lp2 = None
            for attempt in range(1, max_retries + 1):
                lp2 = await run_linux_headless(config, "install-packages", script_dir, on_line, on_task_update)
                if lp2.success:
                    break
                if attempt < max_retries:
                    flog.warning("Linux install-packages attempt %d failed, retrying...", attempt)
                    log.write_info(f"Install packages attempt {attempt} failed, retrying...")
                    await asyncio.sleep(5)
            tasks.set_status("linux_packages", "done" if lp2.success else "failed")
            if not lp2.success:
                log.write_error("Linux install-packages failed")
                status.update("[yellow]Linux package installation had issues. Run verification to check.[/]")

        # Linux: configure xrdp
        if start_index <= task_ids.index("linux_xrdp"):
            log.write_command("Running Linux setup: configure xrdp...")
            tasks.set_status("linux_xrdp", "running")
            lp3 = await run_linux_headless(config, "configure-xrdp", script_dir, on_line, on_task_update)
            tasks.set_status("linux_xrdp", "done" if lp3.success else "failed")
            if not lp3.success:
                log.write_error("Linux configure-xrdp failed")
                status.update("[yellow]xrdp configuration had issues. Run verification to check.[/]")
            else:
                # Set up port proxy so 127.0.0.1:<port> reaches xrdp in WSL
                from ...shared.launcher import ensure_portproxy
                ensure_portproxy(config.xrdpPort, config.distroImportName)
                log.write_success("All tasks complete!")
                status.update("[green]Setup complete! Run verification to confirm.[/]")

        flog.info("=== Setup finished ===")

        # Clear reboot state
        clear_state()

        # Show verify and launcher buttons
        self.query_one("#btn-verify").remove_class("hidden")
        self.query_one("#btn-launcher").remove_class("hidden")

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if not widget_id:
            return
        if widget_id == "btn-reboot":
            import subprocess
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
            self.app.exit()
        elif widget_id == "btn-verify":
            from .verify import VerifyScreen
            self.app.switch_screen(VerifyScreen(self._config))
        elif widget_id == "btn-launcher":
            from .launcher import LauncherScreen
            self.app.switch_screen(LauncherScreen(self._config))
