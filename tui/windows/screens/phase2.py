"""Windows TUI Phase 2 Screen — install, relocate, configure, run Linux setup."""

from __future__ import annotations

import asyncio
import os

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig, windows_to_wsl_path
from ...shared.widgets import LogPanel, TaskListWidget
from ..tasks import wsl_install
from ..tasks.linux_invoke import run_linux_headless
from ..tasks.state import clear_state
from ..tasks.wsl_config import write_wslconfig


PHASE2_TASKS = [
    ("check_drive", "Validate target drive"),
    ("update_wsl", "Update WSL"),
    ("set_version", "Set WSL default version 2"),
    ("install_distro", "Install Ubuntu"),
    ("export_distro", "Export distro"),
    ("import_distro", "Import distro to target drive"),
    ("set_user", "Set default user"),
    ("write_config", "Write .wslconfig"),
    ("shutdown_wsl", "Shutdown WSL"),
    ("linux_phase1", "Linux setup: enable systemd"),
    ("restart_wsl", "Restart WSL"),
    ("linux_phase2", "Linux setup: install packages"),
]


class Phase2Screen(Screen):
    """Phase 2: Install Ubuntu, move to V:, configure, run Linux setup."""

    CSS = """
    #phase2-status {
        padding: 1 2;
        text-style: bold;
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
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield TaskListWidget(PHASE2_TASKS, id="phase2-tasks")
            yield LogPanel(id="phase2-log")
            yield Static("", id="phase2-status")
            with Horizontal(classes="button-bar"):
                yield Static(">> Run Verification <<", id="btn-verify", classes="action-link hidden")

    def on_mount(self) -> None:
        self.run_phase2()

    @work(exclusive=True)
    async def run_phase2(self) -> None:
        tasks = self.query_one("#phase2-tasks", TaskListWidget)
        log = self.query_one("#phase2-log", LogPanel)
        status = self.query_one("#phase2-status", Static)
        config = self._config

        async def on_line(line: str, stream: str) -> None:
            if stream == "stderr":
                log.write_stderr(line)
            else:
                log.write_stdout(line)

        # Helper for task execution
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

        # 1. Check drive
        log.write_command(f"Checking drive {config.wslDriveLetter}:...")
        from ..tasks.validators import check_drive_exists
        result = await check_drive_exists(config.wslDriveLetter, on_line)
        tasks.set_status("check_drive", "done" if result.ok else "failed")
        if not result.ok:
            log.write_error(f"Drive {config.wslDriveLetter}: not found")
            status.update("[red]Target drive not found.[/]")
            return

        # 2. Update WSL
        log.write_command("wsl --update")
        if not await run_task("update_wsl", wsl_install.update_wsl(on_line), "WSL update failed"):
            status.update("[red]WSL update failed.[/]")
            return

        # 3. Set default version
        log.write_command("wsl --set-default-version 2")
        if not await run_task("set_version", wsl_install.set_wsl_default_version(on_line)):
            status.update("[red]Failed to set WSL version.[/]")
            return

        # 4. Install distro
        log.write_command(f"Installing {config.distroName}...")
        if not await run_task("install_distro", wsl_install.install_distro(config, on_line)):
            status.update("[red]Failed to install distro.[/]")
            return

        # 5. Export distro
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

            # 6. Import distro
            log.write_command(f"Importing distro to {config.wslInstallPath}...")
            if not await run_task("import_distro", wsl_install.import_distro(config, tar_path, on_line)):
                status.update("[red]Failed to import distro.[/]")
                return
        else:
            tasks.set_status("export_distro", "failed")
            log.write_error(export_result.message)
            status.update("[red]Failed to export distro.[/]")
            return

        # 7. Set default user
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

        # 8. Write .wslconfig
        log.write_command("Writing .wslconfig...")
        tasks.set_status("write_config", "running")
        wc_result = write_wslconfig(config, overwrite=True)
        if wc_result.ok:
            tasks.set_status("write_config", "done")
            log.write_success(wc_result.message)
        else:
            # Existing config, overwrite
            log.write_info("Overwriting existing .wslconfig...")
            wc_result = write_wslconfig(config, overwrite=True)
            tasks.set_status("write_config", "done" if wc_result.ok else "failed")

        # 9. Shutdown WSL
        log.write_command("wsl --shutdown")
        await run_task("shutdown_wsl", wsl_install.shutdown_wsl(on_line))
        await asyncio.sleep(3)

        # Compute script dir for Linux invocation
        script_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        # 10. Linux Phase 1
        log.write_command("Running Linux setup phase 1 (enable systemd)...")
        tasks.set_status("linux_phase1", "running")

        async def on_task_update(task_id: str, task_status: str) -> None:
            log.write_info(f"  [{task_id}] {task_status}")

        lp1 = await run_linux_headless(config, 1, script_dir, on_line, on_task_update)
        tasks.set_status("linux_phase1", "done" if lp1.success else "failed")
        if not lp1.success:
            log.write_error("Linux phase 1 failed")
            status.update("[red]Linux setup phase 1 failed.[/]")
            return

        # 11. Restart WSL (for systemd)
        log.write_command("Restarting WSL for systemd...")
        await run_task("restart_wsl", wsl_install.shutdown_wsl(on_line))
        await asyncio.sleep(4)

        # 12. Linux Phase 2
        log.write_command("Running Linux setup phase 2 (install packages)...")
        tasks.set_status("linux_phase2", "running")
        lp2 = await run_linux_headless(config, 2, script_dir, on_line, on_task_update)
        tasks.set_status("linux_phase2", "done" if lp2.success else "failed")
        if not lp2.success:
            log.write_error("Linux phase 2 failed")
            status.update("[yellow]Linux setup phase 2 had issues. Run verification to check.[/]")
        else:
            log.write_success("All phases complete!")
            status.update("[green]Setup complete! Run verification to confirm.[/]")

        # Clear the reboot state file
        clear_state()

        # Enable verify button
        self.query_one("#btn-verify").remove_class("hidden")

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if not widget_id:
            return
        if widget_id == "btn-verify":
            from .verify import VerifyScreen
            self.app.switch_screen(VerifyScreen(self._config))
