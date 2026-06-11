"""Apt package management tasks."""

from __future__ import annotations

from ...shared.subprocess_runner import LineCallback, run_local
from ...shared.task_result import TaskResult

# Setup runs apt with no tty and stdin on /dev/null, so any debconf
# prompt (xfce4's display-manager pick, tzdata, conffile questions)
# stalls at "Preconfiguring packages ...". Force non-interactive mode
# and keep existing config files on conflicts; NEEDRESTART_MODE=a stops
# Ubuntu's needrestart from prompting about service restarts.
APT_ENV = "DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a"
APT_OPTS = "-o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold"


async def apt_update(on_line: LineCallback | None = None) -> TaskResult:
    """Run apt update."""
    result = await run_local(f"sudo {APT_ENV} apt update -y", on_line, timeout=300)
    if result.success:
        return TaskResult(ok=True, message="apt update complete")
    return TaskResult(ok=False, message="apt update failed")


async def apt_upgrade(on_line: LineCallback | None = None) -> TaskResult:
    """Run apt upgrade."""
    result = await run_local(
        f"sudo {APT_ENV} apt upgrade -y {APT_OPTS}", on_line, timeout=1800,
    )
    if result.success:
        return TaskResult(ok=True, message="apt upgrade complete")
    return TaskResult(ok=False, message="apt upgrade failed")


async def is_apt_installed(package: str, on_line: LineCallback | None = None) -> bool:
    """Check if an apt package is installed."""
    result = await run_local(
        f"dpkg -l {package} 2>/dev/null | grep -q '^ii' && echo yes || echo no",
        on_line,
        timeout=30,
    )
    return result.output.strip() == "yes"


async def install_apt_package(package: str, on_line: LineCallback | None = None) -> TaskResult:
    """Install a single apt package (idempotent)."""
    if await is_apt_installed(package, on_line):
        return TaskResult(ok=True, message=f"{package} already installed", skipped=True)
    result = await run_local(
        f"sudo {APT_ENV} apt install -y {APT_OPTS} {package}", on_line, timeout=1200,
    )
    if result.success:
        return TaskResult(ok=True, message=f"{package} installed")
    return TaskResult(ok=False, message=f"Failed to install {package}")
