"""Invoke the Linux TUI in headless mode across the WSL boundary."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from ...shared.config import SetupConfig, windows_to_wsl_path
from ...shared.subprocess_runner import LineCallback, SubprocessResult, run_wsl

TaskUpdateCallback = Callable[[str, str], Awaitable[None]]


async def ensure_pip_textual(config: SetupConfig, on_line: LineCallback | None = None) -> bool:
    """Ensure textual is available in WSL (for standalone mode). Not needed for headless."""
    result = await run_wsl(
        config.distroImportName,
        "python3 -c 'import textual' 2>/dev/null && echo ok || echo missing",
        on_line=on_line,
    )
    if "ok" in result.output:
        return True
    # Try installing
    result = await run_wsl(
        config.distroImportName,
        "pip3 install --user textual 2>&1",
        on_line=on_line,
    )
    return result.success


async def run_linux_headless(
    config: SetupConfig,
    phase: int,
    script_dir_win: str,
    on_line: Optional[LineCallback] = None,
    on_task_update: Optional[TaskUpdateCallback] = None,
) -> SubprocessResult:
    """
    Invoke setup_tui_linux.py --headless --phase N inside WSL.

    The headless script outputs structured lines:
        TASK:task_id:status
        LOG:message
        ERROR:message
    """
    wsl_path = windows_to_wsl_path(script_dir_win)
    cmd = f"cd '{wsl_path}' && python3 setup_tui_linux.py --headless --phase {phase}"

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

    return await run_wsl(config.distroImportName, cmd, on_line=parse_line)
