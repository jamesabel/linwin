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
        detail = (
            f"Your Windows build is {build}, but WSL2 requires build 19044 or later.\n"
            "\n"
            "To fix this:\n"
            "  1. Open Settings > Windows Update\n"
            "  2. Install all available updates\n"
            "  3. Reboot and re-run this setup\n"
            "\n"
            "WSL2 requires Windows 10 version 21H2+ or Windows 11."
        )
        return ValidationResult(False, f"Windows build {build} < 19044", detail)
    return ValidationResult(True, f"Windows build {build}", "OK")


async def check_virtualization(on_line: LineCallback | None = None) -> ValidationResult:
    """Check hardware virtualization and related features, with detailed diagnostics on failure."""
    # Gather all virtualization-related info in one PowerShell call
    diag_script = """
$cpu = Get-CimInstance Win32_Processor
$fw = $cpu.VirtualizationFirmwareEnabled
$mfr = $cpu.Manufacturer
$name = $cpu.Name
$hypervisor = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
$wslState = (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -ErrorAction SilentlyContinue).State
$vmState = (Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -ErrorAction SilentlyContinue).State
$hvState = (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -ErrorAction SilentlyContinue).State
Write-Output "FW=$fw"
Write-Output "MFR=$mfr"
Write-Output "CPU=$name"
Write-Output "HYPERVISOR=$hypervisor"
Write-Output "WSL=$wslState"
Write-Output "VMPLATFORM=$vmState"
Write-Output "HYPERV=$hvState"
""".strip()
    result = await run_powershell(diag_script, on_line=on_line)
    if not result.success:
        return ValidationResult(False, "Could not check virtualization")

    # Parse diagnostic output
    info: dict[str, str] = {}
    for line in result.output.strip().splitlines():
        if "=" in line:
            key, _, val = line.partition("=")
            info[key.strip()] = val.strip()

    fw_enabled = info.get("FW", "").lower() == "true"
    hypervisor_present = info.get("HYPERVISOR", "").lower() == "true"
    cpu_name = info.get("CPU", "Unknown")
    mfr = info.get("MFR", "").lower()
    wsl_state = info.get("WSL", "Unknown")
    vm_state = info.get("VMPLATFORM", "Unknown")
    hv_state = info.get("HYPERV", "Unknown")

    is_intel = "intel" in mfr or "genuineintel" in mfr
    bios_tech = "Intel VT-x" if is_intel else "AMD-V (SVM)"
    bios_menu_hint = (
        "look under Advanced > CPU Configuration or Security > Virtualization Technology"
        if is_intel
        else "look under Advanced > CPU Configuration or M.I.T. > SVM Mode"
    )

    if fw_enabled or hypervisor_present:
        return ValidationResult(True, "Virtualization enabled")

    # Build detailed failure report
    lines = [
        "Virtualization diagnostic:",
        f"  Processor:              {cpu_name}",
        f"  BIOS virtualization:    {'Enabled' if fw_enabled else 'DISABLED  <-- action needed'}",
        f"  Hypervisor running:     {'Yes' if hypervisor_present else 'No'}",
        f"  WSL feature:            {wsl_state}",
        f"  Virtual Machine Platform: {vm_state}",
        f"  Hyper-V:                {hv_state}",
        "",
        f"Your processor supports {bios_tech} but it is turned off in BIOS/UEFI.",
        "To fix this:",
        "  1. Restart your PC and enter BIOS/UEFI setup (usually DEL, F2, or F10 at boot)",
        f"  2. In the BIOS menus, {bios_menu_hint}",
        f"  3. Set {bios_tech} to Enabled",
        "  4. Save and exit (usually F10)",
        "  5. Re-run this setup after Windows boots",
    ]
    detail = "\n".join(lines)
    return ValidationResult(False, "Virtualization not enabled in BIOS/UEFI", detail)


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
    # Try to suggest a better drive
    from .drive_scan import scan_drives
    scan = await scan_drives()
    suggestion = ""
    if scan.candidates:
        best = scan.candidates[0]
        suggestion = (
            f"\n"
            f"Recommended drive: {best.letter}: "
            f"({best.type_display}, {best.free_gb} GB free)\n"
        )

    detail = (
        f"Drive {drive_letter}: was not found on this system.\n"
        f"{suggestion}\n"
        "To fix this:\n"
        f"  1. Connect the drive that should be mounted as {drive_letter}:\n"
        "  2. Or use Configure Settings > Scan Drives to pick a drive\n"
    )
    return ValidationResult(False, f"Drive {drive_letter}: not found", detail)


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
