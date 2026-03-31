"""Shared verification check commands used by both Windows and Linux screens.

Each check function takes a ``runner`` — an async callable with the same
signature as ``run_local`` — so the same logic works over ``run_wsl``
(Windows side) or ``run_local`` (Linux side).
"""

from __future__ import annotations

import os
from typing import Awaitable, Callable

from .subprocess_runner import SubprocessResult

# Type alias: an async function that runs a shell command and returns a result.
Runner = Callable[..., Awaitable[SubprocessResult]]


async def check_systemd(runner: Runner) -> tuple[bool, str]:
    """Check if systemd is PID 1. Returns (passed, detail)."""
    result = await runner("ps -p 1 -o comm= 2>/dev/null")
    output = result.output.strip()
    return output == "systemd", output


async def check_snapd(runner: Runner) -> bool:
    """Check if the snapd service is running."""
    result = await runner("systemctl is-active snapd 2>/dev/null")
    return result.output.strip() == "active"


async def check_apt_package(runner: Runner, package: str) -> bool:
    """Check if an apt package is installed."""
    result = await runner(
        f"dpkg -l {package} 2>/dev/null | grep -q '^ii' && echo yes || echo no"
    )
    return result.output.strip() == "yes"


async def check_snap_package(runner: Runner, name: str) -> bool:
    """Check if a snap package is installed."""
    result = await runner(
        f"snap list {name} 2>/dev/null && echo yes || echo no"
    )
    return "yes" in result.output


async def check_display_set() -> tuple[bool, str]:
    """Check if the DISPLAY environment variable is set."""
    value = os.environ.get("DISPLAY", "")
    return bool(value), value


async def check_wslg_dir(runner: Runner) -> bool:
    """Check if /mnt/wslg exists."""
    result = await runner("test -d /mnt/wslg && echo yes || echo no")
    return result.output.strip() == "yes"


async def check_drive_mounted(runner: Runner, drive_letter: str) -> bool:
    """Check if a Windows drive is mounted at /mnt/<letter>."""
    dl = drive_letter.lower()
    result = await runner(f"test -d /mnt/{dl} && echo yes || echo no")
    return result.output.strip() == "yes"
