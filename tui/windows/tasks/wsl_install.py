"""WSL installation, distro management, and relocation tasks."""

from __future__ import annotations

import os
import tempfile

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import LineCallback, SubprocessResult, run_wsl, run_wsl_exec
from ...shared.task_result import TaskResult


async def update_wsl(on_line: LineCallback | None = None) -> TaskResult:
    """Run wsl --update."""
    result = await run_wsl_exec(["--update"], on_line=on_line, timeout=120)
    if result.success:
        return TaskResult(True, "WSL updated")
    return TaskResult(False, "WSL update failed")


async def set_wsl_default_version(on_line: LineCallback | None = None) -> TaskResult:
    """Set WSL default version to 2."""
    result = await run_wsl_exec(["--set-default-version", "2"], on_line=on_line)
    if result.success:
        return TaskResult(True, "Default version set to 2")
    return TaskResult(False, "Failed to set default version")


async def get_registered_distros(on_line: LineCallback | None = None) -> list[str]:
    """Get list of registered WSL distros."""
    result = await run_wsl_exec(["-l", "-q"], on_line=on_line)
    if not result.success:
        return []
    distros = []
    for line in result.stdout_lines:
        cleaned = line.replace("\x00", "").strip()
        if cleaned:
            distros.append(cleaned)
    return distros


async def is_distro_registered(config: SetupConfig, on_line: LineCallback | None = None) -> bool:
    """Check if the target distro is already registered."""
    distros = await get_registered_distros(on_line)
    return config.distroImportName in distros or config.distroName in distros


async def is_distro_on_target_drive(config: SetupConfig, on_line: LineCallback | None = None) -> bool:
    """Check if the distro VHD is already on the target drive."""
    vhd_path = os.path.join(config.wslInstallPath, "ext4.vhdx")
    return os.path.exists(vhd_path)


async def install_distro(config: SetupConfig, on_line: LineCallback | None = None) -> TaskResult:
    """Install the Ubuntu distro via wsl --install. Returns after the install command completes."""
    if await is_distro_registered(config, on_line):
        return TaskResult(True, "Distro already registered", skipped=True)

    result = await run_wsl_exec(
        ["--install", "-d", config.distroName],
        on_line=on_line,
        timeout=600,
    )
    if result.success:
        return TaskResult(True, f"{config.distroName} installed")
    return TaskResult(False, f"Failed to install {config.distroName}")


async def export_distro(config: SetupConfig, on_line: LineCallback | None = None) -> tuple[TaskResult, str]:
    """Export the distro to a temp tar file. Returns (result, tar_path)."""
    if await is_distro_on_target_drive(config, on_line):
        return TaskResult(True, "Distro already on target drive", skipped=True), ""

    # Find the registered name
    distros = await get_registered_distros(on_line)
    current_name = None
    for name in [config.distroImportName, config.distroName]:
        if name in distros:
            current_name = name
            break
    if not current_name:
        return TaskResult(False, "Distro not found in registry"), ""

    export_path = os.path.join(tempfile.gettempdir(), "wsl_ubuntu_export.tar")
    result = await run_wsl_exec(["--export", current_name, export_path], on_line=on_line, timeout=600)
    if result.success:
        return TaskResult(True, f"Exported to {export_path}"), export_path
    return TaskResult(False, "Export failed"), ""


async def import_distro(config: SetupConfig, tar_path: str, on_line: LineCallback | None = None) -> TaskResult:
    """Unregister old distro, import to target path."""
    if await is_distro_on_target_drive(config, on_line):
        return TaskResult(True, "Distro already on target drive", skipped=True)

    # Unregister old
    distros = await get_registered_distros(on_line)
    for name in [config.distroImportName, config.distroName]:
        if name in distros:
            await run_wsl_exec(["--unregister", name], on_line=on_line)

    # Create directory
    os.makedirs(config.wslInstallPath, exist_ok=True)

    # Import
    result = await run_wsl_exec(
        ["--import", config.distroImportName, config.wslInstallPath, tar_path, "--version", "2"],
        on_line=on_line,
        timeout=600,
    )

    # Clean up tar
    try:
        os.remove(tar_path)
    except OSError:
        pass

    if result.success:
        return TaskResult(True, f"Imported to {config.wslInstallPath}")
    return TaskResult(False, "Import failed")


async def detect_default_user(config: SetupConfig, on_line: LineCallback | None = None) -> str | None:
    """Detect the non-root user from /home/ inside the distro."""
    result = await run_wsl(config.distroImportName, "ls /home/ 2>/dev/null", on_line=on_line)
    if result.success and result.stdout_lines:
        users = [u.strip() for u in result.stdout_lines if u.strip() and u.strip() != "root"]
        return users[0] if users else None
    return None


async def set_default_user(config: SetupConfig, username: str, on_line: LineCallback | None = None) -> TaskResult:
    """Set the default user in /etc/wsl.conf."""
    # Check if already set
    check = await run_wsl(
        config.distroImportName,
        "grep -q '\\[user\\]' /etc/wsl.conf 2>/dev/null && echo yes || echo no",
        on_line=on_line,
    )
    if check.output.strip() == "yes":
        return TaskResult(True, "Default user already configured", skipped=True)

    cmd = (
        f"echo '' | sudo tee -a /etc/wsl.conf > /dev/null && "
        f"echo '[user]' | sudo tee -a /etc/wsl.conf > /dev/null && "
        f"echo 'default={username}' | sudo tee -a /etc/wsl.conf > /dev/null"
    )
    result = await run_wsl(config.distroImportName, cmd, on_line=on_line)
    if result.success:
        return TaskResult(True, f"Default user set to {username}")
    return TaskResult(False, "Failed to set default user")


async def shutdown_wsl(on_line: LineCallback | None = None) -> TaskResult:
    """Shut down all WSL instances."""
    result = await run_wsl_exec(["--shutdown"], on_line=on_line)
    return TaskResult(True, "WSL shut down")


async def wait_for_wsl_ready(
    config: SetupConfig, on_line: LineCallback | None = None, max_attempts: int = 10
) -> bool:
    """Wait until the WSL distro is responsive after a restart.

    Probes with a simple 'echo ready' command every 2 seconds.
    Returns True when WSL responds, False if all attempts exhausted.
    """
    import asyncio

    for attempt in range(max_attempts):
        result = await run_wsl(config.distroImportName, "echo ready", on_line=on_line)
        if result.success and "ready" in result.output:
            return True
        await asyncio.sleep(2)
    return False
