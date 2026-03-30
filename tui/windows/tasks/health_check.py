"""Quick startup health check to determine if Ubuntu is ready."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from ...shared.config import SetupConfig
from . import features, wsl_install


@dataclass
class HealthStatus:
    """Result of the quick startup health check."""

    wsl_feature: bool
    vm_platform: bool
    distro_registered: bool
    vhd_on_target: bool

    @property
    def ready(self) -> bool:
        return all([
            self.wsl_feature,
            self.vm_platform,
            self.distro_registered,
            self.vhd_on_target,
        ])

    @property
    def summary_lines(self) -> list[tuple[str, bool]]:
        """Return (label, passed) pairs for display."""
        return [
            ("WSL feature enabled", self.wsl_feature),
            ("Virtual Machine Platform enabled", self.vm_platform),
            (f"Distro registered", self.distro_registered),
            ("Distro VHD on target drive", self.vhd_on_target),
        ]


async def run_health_check(config: SetupConfig) -> HealthStatus:
    """Run all health checks concurrently. Completes in ~2-3 seconds."""
    wsl_feat, vm_plat, distro_reg, vhd_ok = await asyncio.gather(
        features.check_feature("Microsoft-Windows-Subsystem-Linux"),
        features.check_feature("VirtualMachinePlatform"),
        wsl_install.is_distro_registered(config),
        wsl_install.is_distro_on_target_drive(config),
    )
    return HealthStatus(
        wsl_feature=wsl_feat,
        vm_platform=vm_plat,
        distro_registered=distro_reg,
        vhd_on_target=vhd_ok,
    )
