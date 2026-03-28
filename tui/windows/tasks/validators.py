"""Windows prerequisite validation tasks."""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.subprocess_runner import LineCallback, run_powershell


@dataclass
class ValidationResult:
    ok: bool
    message: str
    detail: str = ""


async def check_windows_build(on_line: LineCallback | None = None) -> ValidationResult:
    """Check that Windows build is >= 19044."""
    result = await run_powershell(
        "[System.Environment]::OSVersion.Version.Build",
        on_line=on_line,
    )
    if not result.success:
        return ValidationResult(False, "Could not determine Windows build")
    build_str = result.output.strip()
    try:
        build = int(build_str)
    except ValueError:
        return ValidationResult(False, f"Unexpected build output: {build_str}")
    if build < 19044:
        return ValidationResult(False, f"Windows build {build} < 19044", "Requires Windows 10 21H2+ or Windows 11")
    return ValidationResult(True, f"Windows build {build}", "OK")


async def check_virtualization(on_line: LineCallback | None = None) -> ValidationResult:
    """Check that hardware virtualization is enabled."""
    result = await run_powershell(
        "(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled",
        on_line=on_line,
    )
    if not result.success:
        return ValidationResult(False, "Could not check virtualization")
    output = result.output.strip().lower()
    if output == "true":
        return ValidationResult(True, "Virtualization enabled")
    return ValidationResult(False, "Virtualization not enabled", "Enable Intel VT-x or AMD-V in BIOS/UEFI")


async def check_drive_exists(drive_letter: str, on_line: LineCallback | None = None) -> ValidationResult:
    """Check that the target drive exists."""
    result = await run_powershell(
        f"Test-Path '{drive_letter}:\\'",
        on_line=on_line,
    )
    if not result.success:
        return ValidationResult(False, f"Could not check drive {drive_letter}:")
    output = result.output.strip().lower()
    if output == "true":
        # Get free space
        space_result = await run_powershell(
            f"[math]::Round((Get-PSDrive {drive_letter}).Free / 1GB, 1)",
        )
        free_gb = space_result.output.strip() if space_result.success else "?"
        return ValidationResult(True, f"Drive {drive_letter}: found", f"{free_gb} GB free")
    return ValidationResult(False, f"Drive {drive_letter}: not found")


async def check_ram(on_line: LineCallback | None = None) -> ValidationResult:
    """Detect total system RAM."""
    result = await run_powershell(
        "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)",
        on_line=on_line,
    )
    if not result.success:
        return ValidationResult(True, "RAM: unknown")
    gb = result.output.strip()
    return ValidationResult(True, f"{gb} GB RAM")


async def check_cpu_count(on_line: LineCallback | None = None) -> ValidationResult:
    """Detect CPU core count."""
    result = await run_powershell(
        "(Get-CimInstance Win32_Processor).NumberOfLogicalProcessors",
        on_line=on_line,
    )
    if not result.success:
        return ValidationResult(True, "CPUs: unknown")
    count = result.output.strip()
    return ValidationResult(True, f"{count} logical processors")
