"""Enable systemd in /etc/wsl.conf."""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.subprocess_runner import LineCallback, run_local


@dataclass
class TaskResult:
    ok: bool
    message: str
    skipped: bool = False
    needs_restart: bool = False


async def check_systemd_enabled(on_line: LineCallback | None = None) -> bool:
    """Check if systemd=true is already in wsl.conf."""
    result = await run_local("grep -q 'systemd=true' /etc/wsl.conf 2>/dev/null && echo yes || echo no", on_line)
    return result.output.strip() == "yes"


async def check_systemd_running(on_line: LineCallback | None = None) -> bool:
    """Check if systemd is PID 1."""
    result = await run_local("ps -p 1 -o comm= 2>/dev/null", on_line)
    return result.output.strip() == "systemd"


async def enable_systemd(on_line: LineCallback | None = None) -> TaskResult:
    """Add systemd=true to /etc/wsl.conf if not already present."""
    if await check_systemd_enabled(on_line):
        return TaskResult(ok=True, message="systemd already enabled in wsl.conf", skipped=True)

    # Check if [boot] section exists
    result = await run_local(
        "grep -q '\\[boot\\]' /etc/wsl.conf 2>/dev/null && echo yes || echo no",
        on_line,
    )
    has_boot = result.output.strip() == "yes"

    if has_boot:
        cmd = "sudo sed -i '/\\[boot\\]/a systemd=true' /etc/wsl.conf"
    else:
        cmd = (
            "echo '' | sudo tee -a /etc/wsl.conf > /dev/null && "
            "echo '[boot]' | sudo tee -a /etc/wsl.conf > /dev/null && "
            "echo 'systemd=true' | sudo tee -a /etc/wsl.conf > /dev/null"
        )

    result = await run_local(cmd, on_line)
    if result.success:
        return TaskResult(ok=True, message="systemd enabled in wsl.conf", needs_restart=True)
    return TaskResult(ok=False, message="Failed to modify wsl.conf")
