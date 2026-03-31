"""Headless full verification — returns structured results without UI."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import run_powershell, run_wsl
from . import features, validators, wsl_install
from .wsl_config import check_wslconfig_exists


@dataclass
class VerifyCheckItem:
    name: str
    passed: bool
    detail: str = ""
    warn: bool = False
    category: str = "windows"  # "windows" or "linux"


@dataclass
class VerifyResult:
    checks: list[VerifyCheckItem] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed or c.warn for c in self.checks)

    @property
    def setup_needed(self) -> bool:
        return not self.all_passed

    @property
    def failed_checks(self) -> list[VerifyCheckItem]:
        return [c for c in self.checks if not c.passed and not c.warn]


ProgressCallback = Callable[[VerifyCheckItem], Awaitable[None]] | None


def _add(result: VerifyResult, name: str, passed: bool, detail: str = "",
         warn: bool = False, category: str = "windows") -> VerifyCheckItem:
    item = VerifyCheckItem(name, passed, detail, warn, category)
    result.checks.append(item)
    return item


async def run_full_verification(
    config: SetupConfig,
    on_progress: ProgressCallback = None,
) -> VerifyResult:
    """Run all verification checks and return structured results.

    Args:
        on_progress: Optional async callback invoked after each check completes.
    """
    result = VerifyResult()

    async def _check(name: str, passed: bool, detail: str = "",
                     warn: bool = False, category: str = "windows") -> None:
        item = _add(result, name, passed, detail, warn, category)
        if on_progress:
            await on_progress(item)

    # --- Windows checks ---

    wsl_on = await features.check_feature("Microsoft-Windows-Subsystem-Linux")
    await _check( "WSL feature enabled", wsl_on)

    vm_on = await features.check_feature("VirtualMachinePlatform")
    await _check( "Virtual Machine Platform enabled", vm_on)

    r = await run_powershell("wsl --version 2>&1 | Select-Object -First 1")
    version_str = r.output.strip()
    await _check( "WSL installed", "version" in version_str.lower(), version_str)

    registered = await wsl_install.is_distro_registered(config)
    await _check( f"Distro '{config.distroImportName}' registered", registered)

    if registered:
        info = await run_powershell(
            f"(wsl -l -v 2>&1 | Out-String) -replace '\\0','' "
            f"| Select-String '{config.distroImportName}'"
        )
        version_line = info.output.replace("\x00", "").strip()
        await _check( "Distro is WSL version 2", "2" in version_line, version_line)

    drive_r = await validators.check_drive_exists(config.wslDriveLetter)
    await _check( f"Drive {config.wslDriveLetter}: exists", drive_r.ok, drive_r.detail)

    vhd_path = os.path.join(config.wslInstallPath, "ext4.vhdx")
    await _check( "Distro VHD on target drive", os.path.exists(vhd_path), vhd_path)

    wc_exists, wc_content = check_wslconfig_exists()
    await _check( ".wslconfig exists", wc_exists)

    if wc_exists:
        has_gui = "guiapplications" in wc_content.lower() and "true" in wc_content.lower()
        await _check( "guiApplications=true in .wslconfig", has_gui)

    # --- Linux checks ---

    if registered:
        r = await run_wsl(config.distroImportName, "ps -p 1 -o comm= 2>/dev/null")
        await _check( "systemd is PID 1", r.output.strip() == "systemd",
             r.output.strip(), category="linux")

        r = await run_wsl(config.distroImportName, "systemctl is-active snapd 2>/dev/null")
        await _check( "snapd service running", r.output.strip() == "active", category="linux")

        for pkg in config.aptPackages:
            r = await run_wsl(
                config.distroImportName,
                f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii' && echo yes || echo no",
            )
            await _check( f"apt: {pkg}", r.output.strip() == "yes", category="linux")

        for snap in config.snaps:
            r = await run_wsl(
                config.distroImportName,
                f"snap list {snap.name} 2>/dev/null && echo yes || echo no",
            )
            await _check( f"snap: {snap.name}", "yes" in r.output, category="linux")

        r = await run_wsl(config.distroImportName, "echo $DISPLAY")
        has_display = bool(r.output.strip())
        await _check( "DISPLAY set", has_display, r.output.strip(),
             warn=not has_display, category="linux")

        r = await run_wsl(config.distroImportName, "test -d /mnt/wslg && echo yes || echo no")
        wslg_dir = r.output.strip() == "yes"
        await _check( "/mnt/wslg exists", wslg_dir, warn=not wslg_dir, category="linux")

        r = await run_wsl(
            config.distroImportName,
            "dpkg -l xfce4 2>/dev/null | grep -q '^ii' && echo yes || echo no",
        )
        await _check( "apt: xfce4", r.output.strip() == "yes", category="linux")

        r = await run_wsl(
            config.distroImportName,
            "dpkg -l xrdp 2>/dev/null | grep -q '^ii' && echo yes || echo no",
        )
        await _check( "apt: xrdp", r.output.strip() == "yes", category="linux")

        r = await run_wsl(config.distroImportName, "systemctl is-active xrdp 2>/dev/null")
        await _check( "xrdp service running", r.output.strip() == "active", category="linux")

        r = await run_wsl(
            config.distroImportName,
            "grep -m1 '^port=' /etc/xrdp/xrdp.ini 2>/dev/null",
        )
        await _check( f"xrdp port set to {config.xrdpPort}",
             r.output.strip() == f"port={config.xrdpPort}", category="linux")

        dl = config.wslDriveLetter.lower()
        r = await run_wsl(config.distroImportName, f"test -d /mnt/{dl} && echo yes || echo no")
        mounted = r.output.strip() == "yes"
        await _check( f"/mnt/{dl} mounted", mounted, warn=not mounted, category="linux")
    else:
        await _check( "Distro not registered - skipping Linux checks", False,
             warn=True, category="linux")

    return result
