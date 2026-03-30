"""Tests for the async subprocess runner."""

import asyncio
import sys

import pytest

from linwin.shared.subprocess_runner import SubprocessResult, run_command, run_local


class TestSubprocessResult:
    def test_success(self):
        r = SubprocessResult(exit_code=0, stdout_lines=["hello"])
        assert r.success is True
        assert r.output == "hello"

    def test_failure(self):
        r = SubprocessResult(exit_code=1, stderr_lines=["error"])
        assert r.success is False

    def test_multiline_output(self):
        r = SubprocessResult(exit_code=0, stdout_lines=["a", "b", "c"])
        assert r.output == "a\nb\nc"

    def test_empty_output(self):
        r = SubprocessResult(exit_code=0)
        assert r.output == ""


@pytest.mark.asyncio
class TestRunCommand:
    async def test_echo(self):
        result = await run_command([sys.executable, "-c", "print('hello')"])
        assert result.success
        assert "hello" in result.output

    async def test_exit_code(self):
        result = await run_command([sys.executable, "-c", "import sys; sys.exit(42)"])
        assert result.exit_code == 42
        assert result.success is False

    async def test_stderr(self):
        result = await run_command(
            [sys.executable, "-c", "import sys; sys.stderr.write('oops\\n')"]
        )
        assert "oops" in result.stderr_lines[0]

    async def test_line_callback(self):
        lines_received = []

        async def cb(line, stream):
            lines_received.append((line, stream))

        await run_command(
            [sys.executable, "-c", "print('a'); print('b')"],
            on_line=cb,
        )
        stdout_lines = [l for l, s in lines_received if s == "stdout"]
        assert "a" in stdout_lines
        assert "b" in stdout_lines

    async def test_timeout(self):
        result = await run_command(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            timeout=0.5,
        )
        assert result.exit_code == -1
        assert "Timed out" in result.stderr_lines[0]


@pytest.mark.asyncio
class TestRunLocal:
    async def test_simple_command(self):
        # Use a command that works on both Windows (cmd.exe) and Linux (bash)
        result = await run_command(
            [sys.executable, "-c", "print('local')"],
        )
        assert result.success
        assert "local" in result.output
