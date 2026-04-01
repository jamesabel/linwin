"""Enable WSL and Virtual Machine Platform Windows features.

DISM commands require admin privileges.  When the app is running as a
standard user, ``enable_feature`` uses ``run_elevated`` to request UAC
elevation for just the DISM command, not the entire app.
"""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.subprocess_runner import LineCallback, run_powershell


@dataclass
class FeatureResult:
    already_enabled: bool
    enabled_now: bool
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.already_enabled or self.enabled_now


async def check_feature(feature_name: str, on_line: LineCallback | None = None) -> bool:
    """Check if a Windows optional feature is enabled (does NOT require admin).

    Uses ``wsl --status`` as a lightweight probe: if it succeeds, both the
    WSL and VirtualMachinePlatform features are enabled.  Falls back to
    ``Get-WindowsOptionalFeature`` when running as admin.
    """
    from ..app import check_admin

    if check_admin():
        # Prefer the precise PowerShell check when we have admin.
        result = await run_powershell(
            f"(Get-WindowsOptionalFeature -Online -FeatureName {feature_name}).State",
            on_line=on_line,
        )
        return result.success and result.output.strip().lower() == "enabled"

    # Non-admin: wsl --status succeeds only when both WSL and VM Platform
    # are enabled, which covers both feature names we check.
    from ...shared.subprocess_runner import run_command
    result = await run_command(["wsl.exe", "--status"], on_line=on_line)
    return result.success


async def enable_feature(feature_name: str, on_line: LineCallback | None = None) -> FeatureResult:
    """Enable a Windows optional feature via DISM.

    If not already running as admin, requests UAC elevation for just the
    DISM command.
    """
    is_enabled = await check_feature(feature_name, on_line)
    if is_enabled:
        return FeatureResult(already_enabled=True, enabled_now=False)

    from ..app import check_admin, run_elevated

    dism_cmd = f"dism.exe /online /enable-feature /featurename:{feature_name} /all /norestart"

    if check_admin():
        # Already admin — run directly.
        result = await run_powershell(dism_cmd, on_line=on_line)
        if result.success:
            return FeatureResult(already_enabled=False, enabled_now=True)
        error_msg = "\n".join(result.stderr_lines) if result.stderr_lines else "DISM command failed"
        return FeatureResult(already_enabled=False, enabled_now=False, error=error_msg)
    else:
        # Not admin — elevate just this command.
        success = run_elevated(dism_cmd)
        if success:
            return FeatureResult(already_enabled=False, enabled_now=True)
        return FeatureResult(already_enabled=False, enabled_now=False,
                             error="UAC elevation was denied or DISM command failed")


async def enable_wsl_feature(on_line: LineCallback | None = None) -> FeatureResult:
    """Enable Microsoft-Windows-Subsystem-Linux."""
    return await enable_feature("Microsoft-Windows-Subsystem-Linux", on_line)


async def enable_vm_platform(on_line: LineCallback | None = None) -> FeatureResult:
    """Enable VirtualMachinePlatform."""
    return await enable_feature("VirtualMachinePlatform", on_line)
