"""Structured output protocol for headless (non-TUI) communication.

The headless protocol uses line-based structured output so the Windows
TUI can invoke Linux setup steps over the WSL boundary and parse their
progress.  This module defines both the encoding (used by the headless
runner in ``linwin.linux.__main__``) and decoding (used by the WSL
invoker in ``linwin.windows.tasks.linux_invoke``).

Format::

    TASK:<task_id>:<status>   — task lifecycle event (running/done/skipped/failed)
    LOG:<message>             — informational log line
    ERROR:<message>           — error log line

The status never contains ``:`` but a task id may (e.g. apt package
``libc6:i386``), so TASK lines are split from the right.
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable

from .subprocess_runner import LineCallback

_log = logging.getLogger("wslsetup")

# ── Encoding (producer side) ────────────────────────────────────────


def emit_task(task_id: str, status: str) -> None:
    """Write a TASK line to stdout and the file logger."""
    _log.info("TASK %-25s -> %s", task_id, status)
    print(f"TASK:{task_id}:{status}", flush=True)


def emit_log(msg: str) -> None:
    """Write a LOG line to stdout and the file logger."""
    _log.info("LOG: %s", msg)
    print(f"LOG:{msg}", flush=True)


def emit_error(msg: str) -> None:
    """Write an ERROR line to stdout and the file logger.

    Multi-line messages (e.g. tracebacks) are emitted as one ERROR
    line each — the protocol is line-based, so an unprefixed
    continuation line would lose its error severity at the consumer.
    """
    _log.error("ERROR: %s", msg)
    for part in msg.splitlines() or [""]:
        print(f"ERROR:{part}", flush=True)


# ── Decoding (consumer side) ────────────────────────────────────────

TaskUpdateCallback = Callable[[str, str], Awaitable[None]]


async def parse_headless_line(
    line: str,
    stream: str,
    on_line: LineCallback | None = None,
    on_task_update: TaskUpdateCallback | None = None,
) -> None:
    """Parse a single line of headless protocol output.

    Routes TASK/LOG/ERROR prefixed lines to the appropriate callbacks
    and passes unrecognised lines through to ``on_line``.
    """
    if line.startswith("TASK:"):
        # Split the status from the right: task ids may contain ':'
        # (e.g. apt arch qualifiers like libc6:i386), statuses never do.
        task_id, sep, status = line[5:].rpartition(":")
        if sep and on_task_update:
            await on_task_update(task_id, status)
    elif line.startswith("LOG:"):
        if on_line:
            await on_line(line[4:], "stdout")
    elif line.startswith("ERROR:"):
        if on_line:
            await on_line(line[6:], "stderr")
    else:
        if on_line:
            await on_line(line, stream)
