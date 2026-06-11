"""Async subprocess execution with line-by-line output streaming."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable, Awaitable

from .setup_logging import get_logger

LineCallback = Callable[[str, str], Awaitable[None]]


@dataclass
class SubprocessResult:
    exit_code: int
    stdout_lines: list[str] = field(default_factory=list)
    stderr_lines: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        return "\n".join(self.stdout_lines)


def _kill_quietly(proc: asyncio.subprocess.Process) -> None:
    """Kill a child process, tolerating one that already exited."""
    try:
        proc.kill()
    except (ProcessLookupError, OSError):
        pass


async def run_command(
    args: list[str],
    on_line: LineCallback | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
) -> SubprocessResult:
    """Run a command asynchronously, streaming output line by line."""
    log = get_logger()
    cmd_str = " ".join(args)
    log.info("RUN: %s", cmd_str)
    t0 = time.monotonic()

    env = None
    if args and os.path.basename(args[0]).lower() in ("wsl.exe", "wsl"):
        # Make wsl.exe emit UTF-8 instead of UTF-16LE so non-ASCII
        # distro names survive decoding (the NUL-strip below only
        # round-trips pure ASCII).
        env = {**os.environ, "WSL_UTF8": "1"}

    proc = await asyncio.create_subprocess_exec(
        *args,
        # No child may prompt on the TUI's terminal: without a usable
        # stdin, sudo/OOBE-style prompts fail fast instead of hanging
        # invisibly behind the raw-mode Textual screen.
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def read_stream(
        stream: asyncio.StreamReader,
        name: str,
        accumulator: list[str],
    ) -> None:
        while True:
            raw = await stream.readline()
            if not raw:
                break
            line = raw.decode("utf-8", errors="replace").rstrip("\n\r")
            # Strip null characters from wsl.exe output
            line = line.replace("\x00", "")
            if line or name == "stdout":
                accumulator.append(line)
                if on_line:
                    await on_line(line, name)

    try:
        if timeout:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(proc.stdout, "stdout", stdout_lines),
                    read_stream(proc.stderr, "stderr", stderr_lines),
                ),
                timeout=timeout,
            )
        else:
            await asyncio.gather(
                read_stream(proc.stdout, "stdout", stdout_lines),
                read_stream(proc.stderr, "stderr", stderr_lines),
            )
    except asyncio.TimeoutError:
        _kill_quietly(proc)
        # Reap the killed child so its pipe transports close; otherwise
        # they warn ("I/O operation on closed pipe") at interpreter
        # shutdown when the GC finds them unclosed.
        await proc.wait()
        elapsed = time.monotonic() - t0
        log.warning("TIMEOUT after %.1fs: %s", elapsed, cmd_str)
        return SubprocessResult(exit_code=-1, stdout_lines=stdout_lines, stderr_lines=["Timed out"])
    except BaseException:
        # Cancellation (e.g. the app exits while a probe is in flight):
        # kill and reap the child instead of abandoning its transports.
        _kill_quietly(proc)
        try:
            await proc.wait()
        except BaseException:
            pass
        raise

    await proc.wait()
    elapsed = time.monotonic() - t0
    result = SubprocessResult(
        exit_code=proc.returncode or 0,
        stdout_lines=stdout_lines,
        stderr_lines=stderr_lines,
    )
    if result.success:
        log.info("OK  (exit=0, %.1fs): %s", elapsed, cmd_str)
    else:
        log.warning("FAIL (exit=%d, %.1fs): %s", result.exit_code, elapsed, cmd_str)
    for line in result.stdout_lines:
        if line.strip():
            log.debug("  stdout: %s", line)
    for line in result.stderr_lines:
        if line.strip():
            log.debug("  stderr: %s", line)
    return result


async def run_powershell(
    command: str,
    on_line: LineCallback | None = None,
) -> SubprocessResult:
    """Run a PowerShell command (Windows only)."""
    return await run_command(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        on_line=on_line,
    )


async def run_wsl(
    distro: str,
    command: str,
    on_line: LineCallback | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
) -> SubprocessResult:
    """Run a bash command inside a WSL distro.

    Args:
        cwd: Optional WSL path to set as working directory via --cd flag.
             Use this instead of ``cd '...' &&`` in the command string to
             avoid Windows command-line parsing issues with ``&&``.
        timeout: Optional timeout in seconds; the awaiting flow must never
             block forever on a wedged distro command.
    """
    args = ["wsl.exe", "-d", distro]
    if cwd:
        args.extend(["--cd", cwd])
    args.extend(["--", "bash", "-c", command])
    return await run_command(args, on_line=on_line, timeout=timeout)


async def run_wsl_exec(
    args: list[str],
    on_line: LineCallback | None = None,
    timeout: float | None = None,
) -> SubprocessResult:
    """Run a wsl.exe command directly (e.g., wsl --update)."""
    return await run_command(
        ["wsl.exe"] + args,
        on_line=on_line,
        timeout=timeout,
    )


async def run_local(
    command: str,
    on_line: LineCallback | None = None,
    timeout: float | None = None,
) -> SubprocessResult:
    """Run a local shell command (bash on Linux, cmd on Windows)."""
    if sys.platform == "win32":
        args = ["cmd.exe", "/c", command]
    else:
        args = ["bash", "-c", command]
    return await run_command(args, on_line=on_line, timeout=timeout)
