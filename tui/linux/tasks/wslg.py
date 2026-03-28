"""WSLg verification tasks."""

from __future__ import annotations

import os
from dataclasses import dataclass

from ...shared.subprocess_runner import LineCallback, run_local


@dataclass
class WslgCheckResult:
    display_set: bool
    display_value: str
    wslg_dir_exists: bool
    xeyes_works: bool | None  # None if xeyes not available


async def verify_wslg(on_line: LineCallback | None = None) -> WslgCheckResult:
    """Run all WSLg verification checks."""
    # Check DISPLAY
    display_value = os.environ.get("DISPLAY", "")
    display_set = bool(display_value)

    # Check /mnt/wslg
    result = await run_local("test -d /mnt/wslg && echo yes || echo no", on_line)
    wslg_dir = result.output.strip() == "yes"

    # Test xeyes
    xeyes_works = None
    result = await run_local("command -v xeyes > /dev/null 2>&1 && echo yes || echo no", on_line)
    if result.output.strip() == "yes":
        result = await run_local(
            "xeyes & XPID=$!; sleep 2; kill -0 $XPID 2>/dev/null && echo running || echo stopped; kill $XPID 2>/dev/null",
            on_line,
            timeout=10,
        )
        xeyes_works = "running" in result.output

    return WslgCheckResult(
        display_set=display_set,
        display_value=display_value,
        wslg_dir_exists=wslg_dir,
        xeyes_works=xeyes_works,
    )
