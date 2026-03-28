"""Async subprocess execution with line-by-line output streaming."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional, Awaitable

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


async def run_command(
    args: list[str],
    on_line: Optional[LineCallback] = None,
    cwd: Optional[str] = None,
    timeout: Optional[float] = None,
) -> SubprocessResult:
    """Run a command asynchronously, streaming output line by line."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
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
        proc.kill()
        return SubprocessResult(exit_code=-1, stdout_lines=stdout_lines, stderr_lines=["Timed out"])

    await proc.wait()
    return SubprocessResult(
        exit_code=proc.returncode or 0,
        stdout_lines=stdout_lines,
        stderr_lines=stderr_lines,
    )


async def run_powershell(
    command: str,
    on_line: Optional[LineCallback] = None,
) -> SubprocessResult:
    """Run a PowerShell command (Windows only)."""
    return await run_command(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        on_line=on_line,
    )


async def run_wsl(
    distro: str,
    command: str,
    on_line: Optional[LineCallback] = None,
) -> SubprocessResult:
    """Run a bash command inside a WSL distro."""
    return await run_command(
        ["wsl.exe", "-d", distro, "--", "bash", "-c", command],
        on_line=on_line,
    )


async def run_wsl_exec(
    args: list[str],
    on_line: Optional[LineCallback] = None,
    timeout: Optional[float] = None,
) -> SubprocessResult:
    """Run a wsl.exe command directly (e.g., wsl --update)."""
    return await run_command(
        ["wsl.exe"] + args,
        on_line=on_line,
        timeout=timeout,
    )


async def run_local(
    command: str,
    on_line: Optional[LineCallback] = None,
    timeout: Optional[float] = None,
) -> SubprocessResult:
    """Run a local shell command (bash on Linux, cmd on Windows)."""
    if sys.platform == "win32":
        args = ["cmd.exe", "/c", command]
    else:
        args = ["bash", "-c", command]
    return await run_command(args, on_line=on_line, timeout=timeout)
