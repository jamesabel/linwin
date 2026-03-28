"""Apt package management tasks."""

from __future__ import annotations

from dataclasses import dataclass

from ...shared.subprocess_runner import LineCallback, run_local


@dataclass
class TaskResult:
    ok: bool
    message: str
    skipped: bool = False


async def apt_update(on_line: LineCallback | None = None) -> TaskResult:
    """Run apt update."""
    result = await run_local("sudo apt update -y", on_line, timeout=120)
    if result.success:
        return TaskResult(ok=True, message="apt update complete")
    return TaskResult(ok=False, message="apt update failed")


async def apt_upgrade(on_line: LineCallback | None = None) -> TaskResult:
    """Run apt upgrade."""
    result = await run_local("sudo apt upgrade -y", on_line, timeout=600)
    if result.success:
        return TaskResult(ok=True, message="apt upgrade complete")
    return TaskResult(ok=False, message="apt upgrade failed")


async def is_apt_installed(package: str, on_line: LineCallback | None = None) -> bool:
    """Check if an apt package is installed."""
    result = await run_local(
        f"dpkg -l {package} 2>/dev/null | grep -q '^ii' && echo yes || echo no",
        on_line,
    )
    return result.output.strip() == "yes"


async def install_apt_package(package: str, on_line: LineCallback | None = None) -> TaskResult:
    """Install a single apt package (idempotent)."""
    if await is_apt_installed(package, on_line):
        return TaskResult(ok=True, message=f"{package} already installed", skipped=True)
    result = await run_local(f"sudo apt install -y {package}", on_line, timeout=300)
    if result.success:
        return TaskResult(ok=True, message=f"{package} installed")
    return TaskResult(ok=False, message=f"Failed to install {package}")
