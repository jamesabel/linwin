"""Auto-detect system profile and build an optimized SetupConfig."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from ...shared.config import SetupConfig, WslConfig
from . import validators
from .drive_scan import DriveCandidate, scan_drives


@dataclass
class SystemProfile:
    ram_gb: int
    cpu_count: int
    best_drive: DriveCandidate | None
    all_drives: list[DriveCandidate]


def _parse_int(text: str, default: int = 0) -> int:
    """Extract the first integer from a string."""
    m = re.search(r"\d+", text)
    return int(m.group()) if m else default


async def detect_system_profile() -> SystemProfile:
    """Query system hardware concurrently and return a SystemProfile."""
    ram_result, cpu_result, drive_result = await asyncio.gather(
        validators.check_ram(),
        validators.check_cpu_count(),
        scan_drives(),
    )

    ram_gb = _parse_int(ram_result.message, default=16)
    cpu_count = _parse_int(cpu_result.message, default=4)

    candidates = drive_result.candidates if drive_result.candidates else []
    best_drive = candidates[0] if candidates else None

    return SystemProfile(
        ram_gb=ram_gb,
        cpu_count=cpu_count,
        best_drive=best_drive,
        all_drives=candidates,
    )


def build_auto_config(profile: SystemProfile, base_config: SetupConfig) -> SetupConfig:
    """Build an optimized SetupConfig from detected system profile.

    Overrides hardware-dependent values while preserving user choices
    like distroName, aptPackages, enableSystemd, and xrdpPort.
    """
    # Pick best drive (prefer non-C)
    if profile.best_drive:
        letter = profile.best_drive.letter
    else:
        letter = "C"

    wsl_memory = f"{max(4, profile.ram_gb // 4)}GB"
    wsl_processors = max(1, profile.cpu_count // 2)
    wsl_swap = f"{max(4, profile.ram_gb // 8)}GB"

    return SetupConfig(
        distroName=base_config.distroName,
        distroImportName=base_config.distroImportName,
        wslInstallPath=f"{letter}:\\WSL\\{base_config.distroImportName}",
        wslDriveLetter=letter,
        wslconfig=WslConfig(
            memory=wsl_memory,
            processors=wsl_processors,
            swap=wsl_swap,
            swapFile=f"{letter}:\\WSL\\swap.vhdx",
            guiApplications=True,
            defaultVhdSize="512GB",
        ),
        snaps=[],
        aptPackages=base_config.aptPackages,
        enableSystemd=base_config.enableSystemd,
        xrdpPort=base_config.xrdpPort,
    )
