"""Invoke the Linux TUI in headless mode across the WSL boundary."""

from __future__ import annotations

import base64
import json

from ...shared.config import SetupConfig
from ...shared.headless_protocol import TaskUpdateCallback, parse_headless_line
from ...shared.subprocess_runner import LineCallback, SubprocessResult, run_wsl

# Generous ceiling for a full apt/snap install pass; without one a
# wedged distro command would hang the setup screen forever.
HEADLESS_STEP_TIMEOUT = 3600.0


async def run_linux_headless(
    config: SetupConfig,
    step: str,
    script_dir_win: str,
    on_line: LineCallback | None = None,
    on_task_update: TaskUpdateCallback | None = None,
) -> SubprocessResult:
    """Invoke ``python3 -m linwin.linux --headless --step <step>`` inside WSL.

    The user's SetupConfig is passed along as base64 JSON — the Linux
    side has no access to the Windows pref DB, so without this it would
    silently run with defaults (wrong xrdp port, no optional apps).

    Parses the structured headless protocol output (TASK/LOG/ERROR lines)
    and routes events to the provided callbacks.
    """
    config_b64 = base64.b64encode(json.dumps(config.to_dict()).encode()).decode()
    cmd = f"python3 -m linwin.linux --headless --step {step} --config-b64 {config_b64}"

    async def on_headless_line(line: str, stream: str) -> None:
        await parse_headless_line(line, stream, on_line, on_task_update)

    # Pass the Windows path directly — wsl.exe --cd accepts Windows paths
    # and is more reliable than /mnt/ paths which can trigger ERROR_PATH_NOT_FOUND.
    return await run_wsl(
        config.distroImportName,
        cmd,
        on_line=on_headless_line,
        cwd=script_dir_win,
        timeout=HEADLESS_STEP_TIMEOUT,
    )
