"""Shared verification check commands used by both Windows and Linux screens.

Each check function takes a ``runner`` — an async callable with the same
signature as ``run_local`` — so the same logic works over ``run_wsl``
(Windows side) or ``run_local`` (Linux side).

WSL commands can transiently fail (exit=1, no stdout) due to VM startup
timing.  Functions that hit this use a single retry to avoid false failures.
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

from .subprocess_runner import SubprocessResult

# Type alias: an async function that runs a shell command and returns a result.
Runner = Callable[..., Awaitable[SubprocessResult]]


async def _run_with_retry(runner: Runner, command: str) -> SubprocessResult:
    """Run a command, retrying once if it returns exit!=0 with no output.

    This handles transient WSL failures where the VM isn't fully ready
    and the command exits immediately with no stdout.
    """
    result = await runner(command)
    if not result.success and not result.output.strip():
        await asyncio.sleep(0.5)
        result = await runner(command)
    return result


async def check_systemd(runner: Runner) -> tuple[bool, str]:
    """Check if systemd is PID 1. Returns (passed, detail)."""
    result = await _run_with_retry(runner, "ps -p 1 -o comm= 2>/dev/null")
    output = result.output.strip()
    return output == "systemd", output


async def check_snapd(runner: Runner) -> bool:
    """Check if the snapd service is running."""
    result = await _run_with_retry(runner, "systemctl is-active snapd 2>/dev/null")
    return result.output.strip() == "active"


async def check_apt_package(runner: Runner, package: str) -> bool:
    """Check if an apt package is installed."""
    result = await _run_with_retry(
        runner,
        f"dpkg -l {package} 2>/dev/null | grep -q '^ii' && echo yes || echo no",
    )
    return result.output.strip() == "yes"


async def check_apt_packages(runner: Runner, packages: list[str]) -> dict[str, bool]:
    """Check several apt packages with a single dpkg invocation.

    One subprocess replaces one-per-package; the caller maps the result
    back to per-package checks.

    The command must not contain ``$``: when the runner is ``run_wsl``,
    the wsl.exe relay re-evaluates the command string and expands ``$``
    even inside single quotes (a dpkg-query ``-f '${Package}'`` format
    silently collapses to spaces).
    """
    if not packages:
        return {}
    names = " ".join(packages)
    result = await _run_with_retry(
        runner,
        # "ii  name  version  arch  desc" -> installed package names
        f"dpkg -l {names} 2>/dev/null | grep '^ii' | tr -s ' ' | cut -d' ' -f2 | cut -d: -f1",
    )
    installed = {line.strip() for line in result.stdout_lines if line.strip()}
    return {p: p in installed for p in packages}


async def check_snap_packages(runner: Runner, names: list[str]) -> dict[str, bool]:
    """Check several snap packages with a single ``snap list`` invocation.

    ``$``-free for the same wsl.exe relay reason as check_apt_packages.
    """
    if not names:
        return {}
    result = await _run_with_retry(
        runner, "snap list 2>/dev/null | tail -n +2 | tr -s ' ' | cut -d' ' -f1"
    )
    installed = {line.strip() for line in result.stdout_lines if line.strip()}
    return {n: n in installed for n in names}


async def check_snap_package(runner: Runner, name: str) -> bool:
    """Check if a snap package is installed."""
    result = await _run_with_retry(
        runner,
        f"snap list {name} 2>/dev/null && echo yes || echo no",
    )
    return "yes" in result.output


async def check_command(runner: Runner, name: str) -> bool:
    """Check that a command resolves on the login-shell PATH.

    Login shell so installer-managed paths (npm prefix, /snap/bin) are
    included. ``$``-free for wsl.exe relay safety.
    """
    result = await _run_with_retry(
        runner,
        f"bash -lc 'command -v {name}' > /dev/null 2>&1 && echo yes || echo no",
    )
    return result.output.strip() == "yes"


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
