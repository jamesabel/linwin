"""Snap package management tasks."""

from __future__ import annotations

from ...shared.config import SnapPackage
from ...shared.subprocess_runner import LineCallback, run_local
from ...shared.task_result import TaskResult


async def check_systemd_running(on_line: LineCallback | None = None) -> bool:
    """Snap requires systemd. Check it's running."""
    result = await run_local("systemctl is-system-running 2>/dev/null", on_line)
    output = result.output.strip()
    return output in ("running", "degraded")


async def ensure_snapd(on_line: LineCallback | None = None) -> TaskResult:
    """Ensure snapd is installed and running."""
    # Check if snap command exists
    result = await run_local("command -v snap > /dev/null 2>&1 && echo yes || echo no", on_line)
    if result.output.strip() != "yes":
        install = await run_local("sudo apt install -y snapd", on_line, timeout=120)
        if not install.success:
            return TaskResult(ok=False, message="Failed to install snapd")

    # Enable snapd
    await run_local("sudo systemctl enable --now snapd.socket 2>/dev/null", on_line)
    await run_local("sudo systemctl enable --now snapd 2>/dev/null", on_line)

    # Wait for seed
    await run_local("sudo snap wait system seed.loaded 2>/dev/null || sleep 5", on_line, timeout=30)

    return TaskResult(ok=True, message="snapd is ready")


async def is_snap_installed(name: str, on_line: LineCallback | None = None) -> bool:
    """Check if a snap is installed."""
    result = await run_local(f"snap list {name} 2>/dev/null && echo yes || echo no", on_line)
    return "yes" in result.output


async def install_snap(snap: SnapPackage, on_line: LineCallback | None = None) -> TaskResult:
    """Install a single snap package (idempotent)."""
    if await is_snap_installed(snap.name, on_line):
        return TaskResult(ok=True, message=f"{snap.name} already installed", skipped=True)

    flags = "--classic" if snap.classic else ""
    result = await run_local(f"sudo snap install {flags} {snap.name}", on_line, timeout=300)
    if result.success:
        return TaskResult(ok=True, message=f"{snap.name} installed")
    return TaskResult(ok=False, message=f"Failed to install {snap.name}")
