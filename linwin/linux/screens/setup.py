"""Linux TUI Setup Screen — systemd, apt, snap, WSLg verification."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.widgets import LogPanel, TaskListWidget
from ..tasks import apt, snaps, systemd, wslg


def build_task_list(config: SetupConfig) -> list[tuple[str, str]]:
    """Build the task list dynamically from config."""
    tasks = []
    if config.enableSystemd:
        tasks.append(("enable_systemd", "Enable systemd"))
    tasks.append(("apt_update", "apt update"))
    tasks.append(("apt_upgrade", "apt upgrade"))
    for pkg in config.aptPackages:
        tasks.append((f"apt_{pkg}", f"Install {pkg}"))
    tasks.append(("setup_snapd", "Setup snapd"))
    for snap in config.snaps:
        tasks.append((f"snap_{snap.name}", f"Install {snap.name}"))
    tasks.append(("verify_wslg", "Verify WSLg"))
    return tasks


class SetupScreen(Screen):
    """Run all Linux setup tasks with live progress."""

    CSS = """
    #setup-status {
        padding: 1 2;
        text-style: bold;
    }
    #btn-verify {
        color: $success;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        task_list = build_task_list(self._config)
        with VerticalScroll():
            yield TaskListWidget(task_list, id="setup-tasks")
            yield LogPanel(id="setup-log")
            yield Static("", id="setup-status")
            with Horizontal(classes="button-bar"):
                yield Static(">> Run Verification <<", id="btn-verify", classes="action-link hidden")

    def on_mount(self) -> None:
        self.run_setup()

    @work(exclusive=True)
    async def run_setup(self) -> None:
        tasks = self.query_one("#setup-tasks", TaskListWidget)
        log = self.query_one("#setup-log", LogPanel)
        status = self.query_one("#setup-status", Static)
        config = self._config

        on_line = log.as_line_callback

        # 1. Enable systemd
        if config.enableSystemd:
            tasks.set_status("enable_systemd", "running")
            log.write_command("Enabling systemd...")
            result = await systemd.enable_systemd(on_line)
            if result.skipped:
                tasks.set_status("enable_systemd", "skipped")
                log.write_info("systemd already enabled.")
            elif result.ok:
                tasks.set_status("enable_systemd", "done")
                if result.needs_restart:
                    log.write_info("systemd enabled. WSL restart needed for it to take effect.")
            else:
                tasks.set_status("enable_systemd", "failed")
                log.write_error(result.message)

        # 2. apt update
        tasks.set_status("apt_update", "running")
        log.write_command("sudo apt update -y")
        result = await apt.apt_update(on_line)
        tasks.set_status("apt_update", "done" if result.ok else "failed")

        # 3. apt upgrade
        tasks.set_status("apt_upgrade", "running")
        log.write_command("sudo apt upgrade -y")
        result = await apt.apt_upgrade(on_line)
        tasks.set_status("apt_upgrade", "done" if result.ok else "failed")

        # 4. Install apt packages
        for pkg in config.aptPackages:
            tid = f"apt_{pkg}"
            tasks.set_status(tid, "running")
            log.write_command(f"Installing {pkg}...")
            result = await apt.install_apt_package(pkg, on_line)
            if result.skipped:
                tasks.set_status(tid, "skipped")
                log.write_info(f"{pkg} already installed.")
            elif result.ok:
                tasks.set_status(tid, "done")
            else:
                tasks.set_status(tid, "failed")
                log.write_error(result.message)

        # 5. Setup snapd
        tasks.set_status("setup_snapd", "running")
        log.write_command("Setting up snapd...")
        if not await snaps.check_systemd_running(on_line):
            tasks.set_status("setup_snapd", "failed")
            log.write_error("systemd not running. Snaps require systemd + WSL restart.")
        else:
            result = await snaps.ensure_snapd(on_line)
            tasks.set_status("setup_snapd", "done" if result.ok else "failed")

        # 6. Install snaps
        for snap in config.snaps:
            tid = f"snap_{snap.name}"
            tasks.set_status(tid, "running")
            log.write_command(f"Installing snap: {snap.name}...")
            result = await snaps.install_snap(snap, on_line)
            if result.skipped:
                tasks.set_status(tid, "skipped")
                log.write_info(f"{snap.name} already installed.")
            elif result.ok:
                tasks.set_status(tid, "done")
            else:
                tasks.set_status(tid, "failed")
                log.write_error(result.message)

        # 7. Verify WSLg
        tasks.set_status("verify_wslg", "running")
        log.write_command("Verifying WSLg...")
        wslg_result = await wslg.verify_wslg(on_line)
        wslg_ok = wslg_result.display_set and wslg_result.wslg_dir_exists
        if wslg_result.display_set:
            log.write_success(f"DISPLAY={wslg_result.display_value}")
        else:
            log.write_info("DISPLAY not set.")
        if wslg_result.wslg_dir_exists:
            log.write_success("/mnt/wslg exists")
        else:
            log.write_info("/mnt/wslg not found")
        if wslg_result.xeyes_works is True:
            log.write_success("xeyes launched successfully - WSLg working!")
        elif wslg_result.xeyes_works is False:
            log.write_info("xeyes failed to launch")
        tasks.set_status("verify_wslg", "done" if wslg_ok else "failed")

        # Summary
        log.write_success("\nSetup complete!")
        status.update("[green]Setup complete! Run verification to confirm.[/]")
        self.query_one("#btn-verify").remove_class("hidden")

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if widget_id == "btn-verify":
            from .verify import VerifyScreen
            self.app.switch_screen(VerifyScreen(self._config))
