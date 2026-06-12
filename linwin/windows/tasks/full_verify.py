"""Headless full verification — returns structured results without UI."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from functools import partial
from typing import Awaitable, Callable

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import run_powershell, run_wsl
from ...shared.verify_checks import (
    check_apt_packages,
    check_drive_mounted,
    check_snap_packages,
    check_snapd,
    check_systemd,
    check_wslg_dir,
)
from . import features, validators, wsl_install
from .wsl_config import check_wslconfig_exists


@dataclass
class VerifyCheckItem:
    """A single verification check result with name, status, and optional detail."""

    name: str
    passed: bool
    detail: str = ""
    warn: bool = False
    category: str = "windows"  # "windows" or "linux"


@dataclass
class VerifyResult:
    """Aggregated result of all verification checks."""

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

    # --- Windows checks (independent probes run concurrently) ---

    feature_states, version_r, registered, drive_r = await asyncio.gather(
        features.check_features([
            "Microsoft-Windows-Subsystem-Linux", "VirtualMachinePlatform",
        ]),
        run_powershell("wsl --version 2>&1 | Select-Object -First 1"),
        wsl_install.is_distro_registered(config),
        validators.check_drive_exists(config.wslDriveLetter),
    )

    await _check("WSL feature enabled", feature_states["Microsoft-Windows-Subsystem-Linux"])
    await _check("Virtual Machine Platform enabled", feature_states["VirtualMachinePlatform"])

    version_str = version_r.output.strip()
    await _check("WSL installed", "version" in version_str.lower(), version_str)

    await _check(f"Distro '{config.distroImportName}' registered", registered)

    if registered:
        info = await run_powershell(
            f"(wsl -l -v 2>&1 | Out-String) -replace '\\0','' "
            f"| Select-String '{config.distroImportName}'"
        )
        version_line = info.output.replace("\x00", "").strip()
        await _check("Distro is WSL version 2", "2" in version_line, version_line)

    await _check(f"Drive {config.wslDriveLetter}: exists", drive_r.ok, drive_r.detail)

    vhd_path = os.path.join(config.wslInstallPath, "ext4.vhdx")
    await _check("Distro VHD on target drive", os.path.exists(vhd_path), vhd_path)

    wc_exists, wc_content = check_wslconfig_exists()
    await _check(".wslconfig exists", wc_exists)

    if wc_exists:
        has_gui = "guiapplications" in wc_content.lower() and "true" in wc_content.lower()
        await _check("guiApplications=true in .wslconfig", has_gui)

    # --- Linux checks (concurrent; package checks batched) ---

    if registered:
        # Create a runner that executes commands inside the WSL distro
        wsl_run = partial(run_wsl, config.distroImportName)

        apt_optional = [a.id for a in config.optionalApps if a.install_method == "apt"]
        snap_names = [a.id for a in config.optionalApps if a.install_method == "snap"]
        critical_pkgs = [p for p in ("xfce4", "xrdp") if p not in config.aptPackages]
        all_apt = list(dict.fromkeys(config.aptPackages + apt_optional + critical_pkgs))

        (
            (is_systemd, init_name),
            snapd_ok,
            apt_states,
            snap_states,
            display_r,
            wslg_dir,
            xrdp_r,
            port_r,
            mounted,
        ) = await asyncio.gather(
            check_systemd(wsl_run),
            check_snapd(wsl_run),
            check_apt_packages(wsl_run, all_apt),
            check_snap_packages(wsl_run, snap_names),
            run_wsl(config.distroImportName, "echo $DISPLAY", timeout=60),
            check_wslg_dir(wsl_run),
            run_wsl(config.distroImportName, "systemctl is-active xrdp 2>/dev/null", timeout=60),
            run_wsl(config.distroImportName, "grep -m1 '^port=' /etc/xrdp/xrdp.ini 2>/dev/null", timeout=60),
            check_drive_mounted(wsl_run, config.wslDriveLetter),
        )

        await _check("systemd is PID 1", is_systemd, init_name, category="linux")
        await _check("snapd service running", snapd_ok, category="linux")

        for pkg in config.aptPackages:
            await _check(f"apt: {pkg}", apt_states.get(pkg, False), category="linux")

        for app in config.optionalApps:
            if app.install_method == "snap":
                await _check(f"snap: {app.id}", snap_states.get(app.id, False), category="linux")
            elif app.install_method == "apt":
                await _check(f"apt: {app.id}", apt_states.get(app.id, False), category="linux")

        has_display = bool(display_r.output.strip())
        await _check("DISPLAY set", has_display, display_r.output.strip(),
             warn=not has_display, category="linux")

        await _check("/mnt/wslg exists", wslg_dir, warn=not wslg_dir, category="linux")

        # Check critical xrdp packages only if not already in aptPackages
        for critical_pkg in critical_pkgs:
            await _check(f"apt: {critical_pkg}", apt_states.get(critical_pkg, False), category="linux")

        await _check("xrdp service running", xrdp_r.output.strip() == "active", category="linux")

        await _check(f"xrdp port set to {config.xrdpPort}",
             port_r.output.strip() == f"port={config.xrdpPort}", category="linux")

        dl = config.wslDriveLetter.lower()
        await _check(f"/mnt/{dl} mounted", mounted, warn=not mounted, category="linux")
    else:
        await _check("Distro not registered - skipping Linux checks", False,
             warn=True, category="linux")

    return result
