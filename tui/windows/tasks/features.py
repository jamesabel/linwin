"""Enable WSL and Virtual Machine Platform Windows features."""

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
    """Check if a Windows optional feature is enabled."""
    result = await run_powershell(
        f"(Get-WindowsOptionalFeature -Online -FeatureName {feature_name}).State",
        on_line=on_line,
    )
    return result.success and result.output.strip().lower() == "enabled"


async def enable_feature(feature_name: str, on_line: LineCallback | None = None) -> FeatureResult:
    """Enable a Windows optional feature via DISM. Returns whether it was already enabled or just enabled."""
    is_enabled = await check_feature(feature_name, on_line)
    if is_enabled:
        return FeatureResult(already_enabled=True, enabled_now=False)

    result = await run_powershell(
        f"dism.exe /online /enable-feature /featurename:{feature_name} /all /norestart",
        on_line=on_line,
    )
    if result.success:
        return FeatureResult(already_enabled=False, enabled_now=True)
    error_msg = "\n".join(result.stderr_lines) if result.stderr_lines else "DISM command failed"
    return FeatureResult(already_enabled=False, enabled_now=False, error=error_msg)


async def enable_wsl_feature(on_line: LineCallback | None = None) -> FeatureResult:
    """Enable Microsoft-Windows-Subsystem-Linux."""
    return await enable_feature("Microsoft-Windows-Subsystem-Linux", on_line)


async def enable_vm_platform(on_line: LineCallback | None = None) -> FeatureResult:
    """Enable VirtualMachinePlatform."""
    return await enable_feature("VirtualMachinePlatform", on_line)
