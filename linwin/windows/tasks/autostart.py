"""WSL autostart at Windows logon via a per-user scheduled task.

Lingering systemd user services inside WSL (the xrdp stack, the
OpenClaw gateway) only run while the distro's VM is up — and WSL does
not boot distros at Windows logon by itself. A per-user ONLOGON
scheduled task that runs ``wsl.exe -d <distro> --exec /bin/true``
boots the distro; the lingering services then keep it alive. Per-user
tasks need no admin elevation.
"""

from __future__ import annotations

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import LineCallback, run_command
from ...shared.task_result import TaskResult

TASK_NAME = "linwin-wsl-boot"


async def is_autostart_enabled(on_line: LineCallback | None = None) -> bool:
    """Check whether the logon autostart task exists."""
    result = await run_command(
        ["schtasks.exe", "/Query", "/TN", TASK_NAME],
        on_line=on_line,
        timeout=30,
    )
    return result.success


async def enable_wsl_autostart(config: SetupConfig, on_line: LineCallback | None = None) -> TaskResult:
    """Create (or replace) the per-user logon task that boots the distro."""
    result = await run_command(
        [
            "schtasks.exe", "/Create", "/F",
            "/TN", TASK_NAME,
            "/SC", "ONLOGON",
            "/TR", f"wsl.exe -d {config.distroImportName} --exec /bin/true",
        ],
        on_line=on_line,
        timeout=30,
    )
    if result.success:
        return TaskResult(True, "WSL autostart enabled (starts at Windows logon)")
    return TaskResult(False, "Failed to create the autostart task")


async def disable_wsl_autostart(on_line: LineCallback | None = None) -> TaskResult:
    """Remove the logon autostart task."""
    result = await run_command(
        ["schtasks.exe", "/Delete", "/F", "/TN", TASK_NAME],
        on_line=on_line,
        timeout=30,
    )
    if result.success:
        return TaskResult(True, "WSL autostart disabled")
    return TaskResult(False, "Failed to remove the autostart task")
