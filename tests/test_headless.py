"""Tests for headless entry points in linux.__main__."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from linwin.shared.subprocess_runner import SubprocessResult
from linwin.shared.task_result import TaskResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines())


class TestRunTask:
    def test_run_task_success(self):
        import asyncio
        from linwin.linux.__main__ import _run_task

        async def coro():
            return TaskResult(ok=True, message="done")

        assert _run_task("test", coro()) is True

    def test_run_task_failure(self):
        from linwin.linux.__main__ import _run_task

        async def coro():
            return TaskResult(ok=False, message="failed")

        assert _run_task("test", coro()) is False

    def test_run_task_skipped(self):
        from linwin.linux.__main__ import _run_task

        async def coro():
            return TaskResult(ok=True, message="already done", skipped=True)

        assert _run_task("test", coro()) is True

    def test_run_task_bool_result(self):
        from linwin.linux.__main__ import _run_task

        async def coro():
            return True

        assert _run_task("test", coro()) is True


class TestHeadlessEnableSystemd:
    def test_success(self):
        from linwin.linux.__main__ import headless_enable_systemd
        with patch("linwin.linux.__main__._run_task", return_value=True):
            assert headless_enable_systemd({}) == 0

    def test_failure(self):
        from linwin.linux.__main__ import headless_enable_systemd
        with patch("linwin.linux.__main__._run_task", return_value=False):
            assert headless_enable_systemd({}) == 1


class TestHeadlessInstallPackages:
    def test_success_no_snaps(self):
        from linwin.linux.__main__ import headless_install_packages

        config = {"aptPackages": ["nautilus"], "snaps": []}

        with patch("linwin.linux.__main__._run_task", return_value=True), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", return_value=True), \
             patch("linwin.linux.tasks.snaps.ensure_snapd") as mock_snapd, \
             patch("linwin.linux.tasks.wslg.verify_wslg") as mock_wslg:
            # Mock the async returns
            import asyncio
            mock_snapd.return_value = TaskResult(ok=True, message="ready")
            mock_wslg.return_value = MagicMock(
                display_set=True, display_value=":0",
                wslg_dir_exists=True,
            )
            result = headless_install_packages(config)
            assert result == 0

    def test_systemd_not_running(self):
        from linwin.linux.__main__ import headless_install_packages

        config = {"aptPackages": [], "snaps": []}

        with patch("linwin.linux.__main__._run_task", return_value=True), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", return_value=False), \
             patch("linwin.linux.tasks.wslg.verify_wslg") as mock_wslg:
            mock_wslg.return_value = MagicMock(
                display_set=True, display_value=":0",
                wslg_dir_exists=True,
            )
            result = headless_install_packages(config)
            assert result == 1  # snapd setup failed

    def test_with_snaps(self):
        from linwin.linux.__main__ import headless_install_packages

        config = {"aptPackages": [], "snaps": [{"name": "code", "classic": True}]}

        with patch("linwin.linux.__main__._run_task", return_value=True), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", return_value=True), \
             patch("linwin.linux.tasks.snaps.ensure_snapd") as mock_snapd, \
             patch("linwin.linux.tasks.wslg.verify_wslg") as mock_wslg:
            mock_snapd.return_value = TaskResult(ok=True, message="ready")
            mock_wslg.return_value = MagicMock(
                display_set=True, display_value=":0",
                wslg_dir_exists=True,
            )
            result = headless_install_packages(config)
            assert result == 0


class TestHeadlessConfigureXrdp:
    def test_success(self):
        from linwin.linux.__main__ import headless_configure_xrdp
        config = {"xrdpPort": 3390}
        with patch("linwin.linux.__main__._run_task", return_value=True):
            assert headless_configure_xrdp(config) == 0

    def test_failure(self):
        from linwin.linux.__main__ import headless_configure_xrdp
        config = {"xrdpPort": 3390}
        with patch("linwin.linux.__main__._run_task", return_value=False):
            result = headless_configure_xrdp(config)
            assert result == 1


class TestFindConfig:
    def test_find_config_loads(self):
        from linwin.linux.__main__ import find_config
        data = find_config()
        assert "distroName" in data
        assert isinstance(data, dict)
