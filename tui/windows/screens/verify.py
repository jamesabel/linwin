"""Windows TUI Verification Screen."""

from __future__ import annotations

import os

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import run_powershell, run_wsl
from ...shared.widgets import VerifyDashboard
from ..tasks import features, validators, wsl_install
from ..tasks.wsl_config import check_wslconfig_exists, get_wslconfig_path


class VerifyScreen(Screen):
    """Verification dashboard showing PASS/FAIL/WARN for all checks."""

    CSS = """
    #verify-status {
        padding: 1 2;
        text-style: bold;
    }
    .button-bar {
        height: auto;
        padding: 1 2;
        align-horizontal: center;
    }
    .button-bar Button {
        margin: 0 2;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield VerifyDashboard(title="Windows Checks", id="win-verify")
            yield VerifyDashboard(title="Linux Checks", id="linux-verify")
            yield Static("Running verification...", id="verify-status")
            with Horizontal(classes="button-bar"):
                yield Button("Exit", id="btn-exit", variant="primary")
        yield Footer()

    def on_mount(self) -> None:
        self.run_verification()

    @work(exclusive=True)
    async def run_verification(self) -> None:
        win_dash = self.query_one("#win-verify", VerifyDashboard)
        linux_dash = self.query_one("#linux-verify", VerifyDashboard)
        status = self.query_one("#verify-status", Static)
        config = self._config

        # --- Windows checks ---

        # WSL feature
        wsl_on = await features.check_feature("Microsoft-Windows-Subsystem-Linux")
        win_dash.add_check("WSL feature enabled", wsl_on)

        # VM Platform
        vm_on = await features.check_feature("VirtualMachinePlatform")
        win_dash.add_check("Virtual Machine Platform enabled", vm_on)

        # WSL installed
        result = await run_powershell("wsl --version 2>&1 | Select-Object -First 1")
        win_dash.add_check("WSL installed", result.success, result.output.strip())

        # Distro registered
        registered = await wsl_install.is_distro_registered(config)
        win_dash.add_check(f"Distro '{config.distroImportName}' registered", registered)

        # Distro is WSL 2
        if registered:
            info = await run_powershell(
                f"wsl -l -v 2>&1 | Select-String '{config.distroImportName}'"
            )
            is_v2 = "2" in info.output
            win_dash.add_check("Distro is WSL version 2", is_v2, info.output.strip())

        # Drive exists
        drive_result = await validators.check_drive_exists(config.wslDriveLetter)
        win_dash.add_check(f"Drive {config.wslDriveLetter}: exists", drive_result.ok, drive_result.detail)

        # VHD on target drive
        vhd_path = os.path.join(config.wslInstallPath, "ext4.vhdx")
        vhd_exists = os.path.exists(vhd_path)
        win_dash.add_check("Distro VHD on target drive", vhd_exists, vhd_path)

        # .wslconfig
        wc_exists, wc_content = check_wslconfig_exists()
        win_dash.add_check(".wslconfig exists", wc_exists, get_wslconfig_path())

        if wc_exists:
            has_gui = "guiapplications" in wc_content.lower() and "true" in wc_content.lower()
            win_dash.add_check("guiApplications=true in .wslconfig", has_gui)

        # --- Linux checks ---
        if registered:
            # systemd
            result = await run_wsl(config.distroImportName, "ps -p 1 -o comm= 2>/dev/null")
            is_systemd = result.output.strip() == "systemd"
            linux_dash.add_check("systemd is PID 1", is_systemd, result.output.strip())

            # snapd
            result = await run_wsl(config.distroImportName, "systemctl is-active snapd 2>/dev/null")
            snapd_ok = result.output.strip() == "active"
            linux_dash.add_check("snapd service running", snapd_ok)

            # apt packages
            for pkg in config.aptPackages:
                result = await run_wsl(
                    config.distroImportName,
                    f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii' && echo yes || echo no",
                )
                linux_dash.add_check(f"apt: {pkg}", result.output.strip() == "yes")

            # snap packages
            for snap in config.snaps:
                result = await run_wsl(
                    config.distroImportName,
                    f"snap list {snap.name} 2>/dev/null && echo yes || echo no",
                )
                linux_dash.add_check(f"snap: {snap.name}", "yes" in result.output)

            # WSLg
            result = await run_wsl(config.distroImportName, "echo $DISPLAY")
            has_display = bool(result.output.strip())
            linux_dash.add_check("DISPLAY set", has_display, result.output.strip(), warn=not has_display)

            result = await run_wsl(config.distroImportName, "test -d /mnt/wslg && echo yes || echo no")
            wslg_dir = result.output.strip() == "yes"
            linux_dash.add_check("/mnt/wslg exists", wslg_dir, warn=not wslg_dir)

            # V: mount
            dl = config.wslDriveLetter.lower()
            result = await run_wsl(config.distroImportName, f"test -d /mnt/{dl} && echo yes || echo no")
            mounted = result.output.strip() == "yes"
            linux_dash.add_check(f"/mnt/{dl} mounted", mounted, warn=not mounted)
        else:
            linux_dash.add_check("Distro not registered - skipping Linux checks", False, warn=True)

        # Summary
        total_failed = (
            (win_dash._failed if hasattr(win_dash, "_failed") else 0)
            + (linux_dash._failed if hasattr(linux_dash, "_failed") else 0)
        )
        if total_failed == 0:
            status.update("[green]All checks passed![/]")
        else:
            status.update(f"[red]{total_failed} check(s) failed. See details above.[/]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-exit":
            self.app.exit()
