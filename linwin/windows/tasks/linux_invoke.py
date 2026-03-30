"""Invoke the Linux TUI in headless mode across the WSL boundary."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import LineCallback, SubprocessResult, run_wsl

TaskUpdateCallback = Callable[[str, str], Awaitable[None]]


async def run_linux_headless(
    config: SetupConfig,
    step: str,
    script_dir_win: str,
    on_line: Optional[LineCallback] = None,
    on_task_update: Optional[TaskUpdateCallback] = None,
) -> SubprocessResult:
    """
    Invoke python3 -m linwin.linux --headless --step <step> inside WSL.

    The headless script outputs structured lines:
        TASK:task_id:status
        LOG:message
        ERROR:message
    """
    cmd = f"python3 -m linwin.linux --headless --step {step}"

    async def parse_line(line: str, stream: str) -> None:
        if line.startswith("TASK:"):
            parts = line.split(":", 2)
            if len(parts) == 3 and on_task_update:
                await on_task_update(parts[1], parts[2])
        elif line.startswith("LOG:"):
            if on_line:
                await on_line(line[4:], "stdout")
        elif line.startswith("ERROR:"):
            if on_line:
                await on_line(line[6:], "stderr")
        else:
            if on_line:
                await on_line(line, stream)

    # Pass the Windows path directly — wsl.exe --cd accepts Windows paths
    # and is more reliable than /mnt/ paths which can trigger ERROR_PATH_NOT_FOUND.
    return await run_wsl(config.distroImportName, cmd, on_line=parse_line, cwd=script_dir_win)
