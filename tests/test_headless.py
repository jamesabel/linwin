"""Tests for headless entry points in linux.__main__ and the shared step runner."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from linwin.shared.config import AppEntry, SetupConfig
from linwin.shared.subprocess_runner import SubprocessResult
from linwin.shared.task_result import TaskResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines())


class RecordingReporter:
    """StepReporter that records every status/log call."""

    def __init__(self) -> None:
        self.statuses: list[tuple[str, str]] = []
        self.errors: list[str] = []
        self.infos: list[str] = []
        self.details: dict[str, str] = {}

    def set_status(self, task_id: str, status: str, detail: str = "") -> None:
        self.statuses.append((task_id, status))
        if detail:
            self.details[task_id] = detail

    def command(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    def error(self, msg: str) -> None:
        self.errors.append(msg)


def _step(task_id: str, result: TaskResult, requires_snapd: bool = False):
    from linwin.linux.tasks.steps import SetupStep

    async def run(on_line=None):
        return result

    return SetupStep(task_id, task_id, run, requires_snapd=requires_snapd)


class TestRunSteps:
    def test_success(self):
        import asyncio
        from linwin.linux.tasks.steps import run_steps

        reporter = RecordingReporter()
        ok = asyncio.run(run_steps([_step("t", TaskResult(ok=True, message="done"))], reporter))
        assert ok is True
        assert ("t", "running") in reporter.statuses
        assert ("t", "done") in reporter.statuses

    def test_failure(self):
        import asyncio
        from linwin.linux.tasks.steps import run_steps

        reporter = RecordingReporter()
        ok = asyncio.run(run_steps([_step("t", TaskResult(ok=False, message="boom"))], reporter))
        assert ok is False
        assert ("t", "failed") in reporter.statuses
        assert "boom" in reporter.errors

    def test_skipped(self):
        import asyncio
        from linwin.linux.tasks.steps import run_steps

        reporter = RecordingReporter()
        ok = asyncio.run(run_steps([_step("t", TaskResult(ok=True, message="already", skipped=True))], reporter))
        assert ok is True
        assert ("t", "skipped") in reporter.statuses
        # The skip reason must travel with the status.
        assert reporter.details["t"] == "already"

    def test_snapd_failure_gates_snap_steps(self):
        import asyncio
        from linwin.linux.tasks.steps import SNAPD_STEP_ID, run_steps

        reporter = RecordingReporter()
        steps = [
            _step(SNAPD_STEP_ID, TaskResult(ok=False, message="no snapd")),
            _step("snap_code", TaskResult(ok=True, message="installed"), requires_snapd=True),
            _step("apt_opt_gedit", TaskResult(ok=True, message="installed")),
        ]
        ok = asyncio.run(run_steps(steps, reporter))
        assert ok is False
        assert (SNAPD_STEP_ID, "failed") in reporter.statuses
        # snap step never ran; apt step did
        assert ("snap_code", "failed") in reporter.statuses
        assert ("snap_code", "running") not in reporter.statuses
        assert ("apt_opt_gedit", "done") in reporter.statuses


class TestHeadlessEnableSystemd:
    def test_success(self):
        from linwin.linux.__main__ import headless_enable_systemd
        with patch("linwin.linux.tasks.systemd.enable_systemd", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="enabled")):
            assert headless_enable_systemd(SetupConfig()) == 0

    def test_failure(self):
        from linwin.linux.__main__ import headless_enable_systemd
        with patch("linwin.linux.tasks.systemd.enable_systemd", new_callable=AsyncMock,
                   return_value=TaskResult(ok=False, message="failed")):
            assert headless_enable_systemd(SetupConfig()) == 1

    def test_disabled_in_config(self):
        from linwin.linux.__main__ import headless_enable_systemd
        config = SetupConfig()
        config.enableSystemd = False
        with patch("linwin.linux.tasks.systemd.enable_systemd", new_callable=AsyncMock) as mock_enable:
            assert headless_enable_systemd(config) == 0
            mock_enable.assert_not_called()


def _packages_patches(apt_ok: bool = True, systemd_running: bool = True, snapd_ok: bool = True):
    tr = lambda ok, msg: TaskResult(ok=ok, message=msg)
    return [
        patch("linwin.linux.tasks.apt.apt_update", new_callable=AsyncMock,
              return_value=tr(True, "ok")),
        patch("linwin.linux.tasks.apt.apt_upgrade", new_callable=AsyncMock,
              return_value=tr(True, "ok")),
        patch("linwin.linux.tasks.apt.install_apt_package", new_callable=AsyncMock,
              return_value=tr(apt_ok, "installed" if apt_ok else "failed")),
        patch("linwin.linux.tasks.snaps.check_systemd_running", new_callable=AsyncMock,
              return_value=systemd_running),
        patch("linwin.linux.tasks.snaps.ensure_snapd", new_callable=AsyncMock,
              return_value=tr(snapd_ok, "ready" if snapd_ok else "fail")),
        patch("linwin.linux.tasks.snaps.install_snap", new_callable=AsyncMock,
              return_value=tr(True, "installed")),
        patch("linwin.linux.tasks.wslg.verify_wslg", new_callable=AsyncMock,
              return_value=MagicMock(display_set=True, display_value=":0",
                                     wslg_dir_exists=True, xeyes_works=True)),
    ]


class TestHeadlessInstallPackages:
    def _run(self, config: SetupConfig, **kwargs) -> int:
        from contextlib import ExitStack
        from linwin.linux.__main__ import headless_install_packages

        with ExitStack() as stack:
            for p in _packages_patches(**kwargs):
                stack.enter_context(p)
            return headless_install_packages(config)

    def test_success_no_snaps(self):
        config = SetupConfig()
        config.aptPackages = ["nautilus"]
        config.optionalApps = []
        assert self._run(config) == 0

    def test_systemd_not_running(self):
        config = SetupConfig()
        config.aptPackages = []
        config.optionalApps = []
        assert self._run(config, systemd_running=False) == 1  # snapd setup failed

    def test_with_snaps(self):
        config = SetupConfig()
        config.aptPackages = []
        config.optionalApps = [AppEntry("code", "VS Code", "code", "snap")]
        assert self._run(config) == 0

    def test_apt_failure(self):
        config = SetupConfig()
        config.aptPackages = ["nautilus"]
        config.optionalApps = []
        assert self._run(config, apt_ok=False) == 1

    def test_snapd_fails(self):
        config = SetupConfig()
        config.aptPackages = []
        config.optionalApps = []
        assert self._run(config, snapd_ok=False) == 1


class TestHeadlessConfigureXrdp:
    def _run(self, ok: bool) -> int:
        from contextlib import ExitStack
        from linwin.linux.__main__ import headless_configure_xrdp

        tr = TaskResult(ok=ok, message="ok" if ok else "fail")
        patches = [
            patch("linwin.linux.tasks.xrdp.install_xrdp", new_callable=AsyncMock, return_value=tr),
            patch("linwin.linux.tasks.xrdp.configure_xrdp_port", new_callable=AsyncMock, return_value=tr),
            patch("linwin.linux.tasks.xrdp.configure_xrdp_session", new_callable=AsyncMock, return_value=tr),
            patch("linwin.linux.tasks.xrdp.configure_default_browser", new_callable=AsyncMock, return_value=tr),
            patch("linwin.linux.tasks.xrdp.enable_xrdp_service", new_callable=AsyncMock, return_value=tr),
        ]
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            return headless_configure_xrdp(SetupConfig())

    def test_success(self):
        assert self._run(ok=True) == 0

    def test_failure(self):
        assert self._run(ok=False) == 1


class TestFindConfig:
    def test_find_config_loads(self):
        from linwin.linux.__main__ import find_config
        data = find_config()
        assert "distroName" in data
        assert isinstance(data, dict)

    def test_config_b64_round_trip(self):
        """The base64 config arg must round-trip into an equivalent SetupConfig."""
        import base64
        import json

        config = SetupConfig()
        config.xrdpPort = 3395
        config.optionalApps = [AppEntry("code", "VS Code", "code", "snap")]
        b64 = base64.b64encode(json.dumps(config.to_dict()).encode()).decode()
        restored = SetupConfig.from_dict(json.loads(base64.b64decode(b64)))
        assert restored.xrdpPort == 3395
        assert [a.id for a in restored.optionalApps] == ["code"]
        assert restored == config
