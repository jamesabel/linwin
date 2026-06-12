"""Tests for shared/verify_checks.py — batch helpers, retry, env checks."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from linwin.shared.subprocess_runner import SubprocessResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines())


def _runner(result: SubprocessResult):
    async def run(command: str, *args, **kwargs) -> SubprocessResult:
        run.commands.append(command)
        return result
    run.commands = []
    return run


@pytest.mark.asyncio
class TestBatchHelpers:
    async def test_check_apt_packages_mixed(self):
        from linwin.shared.verify_checks import check_apt_packages
        # The grep '^ii' pipeline emits one installed package name per line
        runner = _runner(_ok("nautilus\nxrdp\n"))
        states = await check_apt_packages(runner, ["nautilus", "xrdp", "missing"])
        assert states == {"nautilus": True, "xrdp": True, "missing": False}
        # One subprocess for the whole batch, and no '$' — the wsl.exe
        # relay expands $ even inside single quotes.
        assert len(runner.commands) == 1
        assert "dpkg -l" in runner.commands[0]
        assert "$" not in runner.commands[0]

    async def test_check_apt_packages_empty(self):
        from linwin.shared.verify_checks import check_apt_packages
        runner = _runner(_ok())
        assert await check_apt_packages(runner, []) == {}
        assert runner.commands == []  # no subprocess for nothing

    async def test_check_snap_packages(self):
        from linwin.shared.verify_checks import check_snap_packages
        runner = _runner(_ok("code\nfirefox\n"))
        states = await check_snap_packages(runner, ["code", "gimp"])
        assert states == {"code": True, "gimp": False}
        assert len(runner.commands) == 1
        assert "$" not in runner.commands[0]

    async def test_check_snap_packages_empty(self):
        from linwin.shared.verify_checks import check_snap_packages
        runner = _runner(_ok())
        assert await check_snap_packages(runner, []) == {}
        assert runner.commands == []


@pytest.mark.asyncio
class TestRetry:
    async def test_retries_once_on_silent_failure(self):
        from linwin.shared.verify_checks import _run_with_retry
        results = [_fail(), _ok("yes")]
        calls = []

        async def runner(command: str, *args, **kwargs) -> SubprocessResult:
            calls.append(command)
            return results[len(calls) - 1]

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await _run_with_retry(runner, "echo yes")
        assert result.output == "yes"
        assert len(calls) == 2

    async def test_no_retry_when_output_present(self):
        from linwin.shared.verify_checks import _run_with_retry
        calls = []

        async def runner(command: str, *args, **kwargs) -> SubprocessResult:
            calls.append(command)
            return _fail("error text")

        result = await _run_with_retry(runner, "boom")
        assert not result.success
        assert len(calls) == 1


@pytest.mark.asyncio
class TestEnvChecks:
    async def test_check_display_set(self, monkeypatch):
        from linwin.shared.verify_checks import check_display_set
        monkeypatch.setenv("DISPLAY", ":0")
        ok, value = await check_display_set()
        assert ok and value == ":0"

    async def test_check_display_unset(self, monkeypatch):
        from linwin.shared.verify_checks import check_display_set
        monkeypatch.delenv("DISPLAY", raising=False)
        ok, value = await check_display_set()
        assert not ok and value == ""

    async def test_check_wslg_dir(self):
        from linwin.shared.verify_checks import check_wslg_dir
        assert await check_wslg_dir(_runner(_ok("yes"))) is True
        assert await check_wslg_dir(_runner(_ok("no"))) is False

    async def test_check_drive_mounted(self):
        from linwin.shared.verify_checks import check_drive_mounted
        runner = _runner(_ok("yes"))
        assert await check_drive_mounted(runner, "V") is True
        assert "/mnt/v" in runner.commands[0]
