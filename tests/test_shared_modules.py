"""Tests for shared modules: headless_protocol, verify_checks, launcher, base_app, config helpers, widgets."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linwin.shared.config import SetupConfig
from linwin.shared.subprocess_runner import SubprocessResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines())


# ── headless_protocol ────────────────────────────────────────────────


class TestHeadlessProtocolEmit:
    def test_emit_task(self, capsys):
        from linwin.shared.headless_protocol import emit_task
        emit_task("apt_update", "running")
        captured = capsys.readouterr()
        assert "TASK:apt_update:running" in captured.out

    def test_emit_log(self, capsys):
        from linwin.shared.headless_protocol import emit_log
        emit_log("Installing package")
        captured = capsys.readouterr()
        assert "LOG:Installing package" in captured.out

    def test_emit_error(self, capsys):
        from linwin.shared.headless_protocol import emit_error
        emit_error("Something failed")
        captured = capsys.readouterr()
        assert "ERROR:Something failed" in captured.out


@pytest.mark.asyncio
class TestHeadlessProtocolParse:
    async def test_parse_task_line(self):
        from linwin.shared.headless_protocol import parse_headless_line
        on_task = AsyncMock()
        await parse_headless_line("TASK:apt_update:done", "stdout", on_task_update=on_task)
        on_task.assert_called_once_with("apt_update", "done")

    async def test_parse_log_line(self):
        from linwin.shared.headless_protocol import parse_headless_line
        on_line = AsyncMock()
        await parse_headless_line("LOG:hello world", "stdout", on_line=on_line)
        on_line.assert_called_once_with("hello world", "stdout")

    async def test_parse_error_line(self):
        from linwin.shared.headless_protocol import parse_headless_line
        on_line = AsyncMock()
        await parse_headless_line("ERROR:bad stuff", "stderr", on_line=on_line)
        on_line.assert_called_once_with("bad stuff", "stderr")

    async def test_parse_regular_line(self):
        from linwin.shared.headless_protocol import parse_headless_line
        on_line = AsyncMock()
        await parse_headless_line("some output", "stdout", on_line=on_line)
        on_line.assert_called_once_with("some output", "stdout")

    async def test_parse_task_malformed(self):
        from linwin.shared.headless_protocol import parse_headless_line
        on_task = AsyncMock()
        await parse_headless_line("TASK:incomplete", "stdout", on_task_update=on_task)
        on_task.assert_not_called()

    async def test_parse_no_callbacks(self):
        from linwin.shared.headless_protocol import parse_headless_line
        # Should not raise even with no callbacks
        await parse_headless_line("LOG:ignored", "stdout")
        await parse_headless_line("TASK:x:y", "stdout")
        await parse_headless_line("ERROR:ignored", "stderr")
        await parse_headless_line("plain", "stdout")


# ── verify_checks ────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestVerifyChecks:
    async def test_check_systemd_true(self):
        from linwin.shared.verify_checks import check_systemd
        runner = AsyncMock(return_value=_ok("systemd"))
        passed, detail = await check_systemd(runner)
        assert passed is True
        assert detail == "systemd"

    async def test_check_systemd_false(self):
        from linwin.shared.verify_checks import check_systemd
        runner = AsyncMock(return_value=_ok("init"))
        passed, detail = await check_systemd(runner)
        assert passed is False

    async def test_check_snapd_true(self):
        from linwin.shared.verify_checks import check_snapd
        runner = AsyncMock(return_value=_ok("active"))
        assert await check_snapd(runner) is True

    async def test_check_snapd_false(self):
        from linwin.shared.verify_checks import check_snapd
        runner = AsyncMock(return_value=_ok("inactive"))
        assert await check_snapd(runner) is False

    async def test_check_apt_package_installed(self):
        from linwin.shared.verify_checks import check_apt_package
        runner = AsyncMock(return_value=_ok("yes"))
        assert await check_apt_package(runner, "nautilus") is True

    async def test_check_apt_package_missing(self):
        from linwin.shared.verify_checks import check_apt_package
        runner = AsyncMock(return_value=_ok("no"))
        assert await check_apt_package(runner, "nautilus") is False

    async def test_check_snap_package_installed(self):
        from linwin.shared.verify_checks import check_snap_package
        runner = AsyncMock(return_value=_ok("code 1.80 yes"))
        assert await check_snap_package(runner, "code") is True

    async def test_check_snap_package_missing(self):
        from linwin.shared.verify_checks import check_snap_package
        runner = AsyncMock(return_value=_ok("no"))
        assert await check_snap_package(runner, "code") is False

    async def test_check_display_set(self):
        from linwin.shared.verify_checks import check_display_set
        with patch.dict("os.environ", {"DISPLAY": ":0"}):
            ok, val = await check_display_set()
            assert ok
            assert val == ":0"

    async def test_check_display_not_set(self):
        from linwin.shared.verify_checks import check_display_set
        with patch.dict("os.environ", {}, clear=True):
            ok, val = await check_display_set()
            assert not ok

    async def test_check_wslg_dir_exists(self):
        from linwin.shared.verify_checks import check_wslg_dir
        runner = AsyncMock(return_value=_ok("yes"))
        assert await check_wslg_dir(runner) is True

    async def test_check_wslg_dir_missing(self):
        from linwin.shared.verify_checks import check_wslg_dir
        runner = AsyncMock(return_value=_ok("no"))
        assert await check_wslg_dir(runner) is False

    async def test_check_drive_mounted(self):
        from linwin.shared.verify_checks import check_drive_mounted
        runner = AsyncMock(return_value=_ok("yes"))
        assert await check_drive_mounted(runner, "V") is True

    async def test_check_drive_not_mounted(self):
        from linwin.shared.verify_checks import check_drive_mounted
        runner = AsyncMock(return_value=_ok("no"))
        assert await check_drive_mounted(runner, "V") is False


# ── launcher ─────────────────────────────────────────────────────────


class TestLauncher:
    def test_notify_launch_success(self):
        from linwin.shared.launcher import notify_launch
        app = MagicMock()
        with patch("linwin.shared.launcher.launch_wsl_app"):
            notify_launch(app, "nautilus", "File Manager", "Ubuntu")
            app.notify.assert_called_once()
            assert "Launched" in app.notify.call_args[0][0]

    def test_notify_launch_failure(self):
        from linwin.shared.launcher import notify_launch
        app = MagicMock()
        with patch("linwin.shared.launcher.launch_wsl_app", side_effect=RuntimeError("fail")):
            notify_launch(app, "nautilus", "File Manager", "Ubuntu")
            app.notify.assert_called_once()
            assert app.notify.call_args[1]["severity"] == "error"

    def test_launch_wsl_app(self):
        from linwin.shared.launcher import launch_wsl_app
        with patch("linwin.shared.launcher.subprocess.Popen") as mock_popen, \
             patch("linwin.shared.launcher.ensure_wsl_keepalive"):
            launch_wsl_app("Ubuntu", "nautilus")
            mock_popen.assert_called_once()

    def test_launch_windows_terminal(self):
        from linwin.shared.launcher import launch_windows_terminal
        with patch("linwin.shared.launcher.subprocess.Popen") as mock_popen:
            launch_windows_terminal("Ubuntu")
            mock_popen.assert_called_once()

    def test_launch_rdp(self):
        from linwin.shared.launcher import launch_rdp
        with patch("linwin.shared.launcher.ensure_portproxy"), \
             patch("linwin.shared.launcher.ensure_wsl_keepalive"), \
             patch("linwin.shared.launcher.subprocess.Popen") as mock_popen:
            launch_rdp(3390, "Ubuntu")
            mock_popen.assert_called_once()

    def test_ensure_wsl_keepalive_starts(self):
        from linwin.shared import launcher
        launcher._keepalive_proc = None
        with patch("linwin.shared.launcher.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            launcher.ensure_wsl_keepalive("Ubuntu")
            mock_popen.assert_called_once()

    def test_ensure_wsl_keepalive_already_running(self):
        from linwin.shared import launcher
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # Still running
        launcher._keepalive_proc = mock_proc
        with patch("linwin.shared.launcher.subprocess.Popen") as mock_popen:
            launcher.ensure_wsl_keepalive("Ubuntu")
            mock_popen.assert_not_called()
        launcher._keepalive_proc = None  # Clean up

    def test_ensure_portproxy(self):
        from linwin.shared.launcher import ensure_portproxy
        with patch("linwin.shared.launcher._get_wsl_ip", return_value="172.20.0.1"), \
             patch("linwin.shared.launcher.subprocess.run") as mock_run:
            ensure_portproxy(3390, "Ubuntu")
            mock_run.assert_called_once()

    def test_ensure_portproxy_no_ip(self):
        from linwin.shared.launcher import ensure_portproxy
        with patch("linwin.shared.launcher._get_wsl_ip", return_value=""), \
             patch("linwin.shared.launcher.subprocess.run") as mock_run:
            ensure_portproxy(3390, "Ubuntu")
            mock_run.assert_not_called()

    def test_get_wsl_ip_success(self):
        from linwin.shared.launcher import _get_wsl_ip
        mock_result = MagicMock()
        mock_result.stdout = "172.20.0.1 "
        with patch("linwin.shared.launcher.subprocess.run", return_value=mock_result):
            ip = _get_wsl_ip("Ubuntu")
            assert ip == "172.20.0.1"

    def test_get_wsl_ip_failure(self):
        from linwin.shared.launcher import _get_wsl_ip
        with patch("linwin.shared.launcher.subprocess.run", side_effect=RuntimeError("fail")):
            ip = _get_wsl_ip("Ubuntu")
            assert ip == ""


# ── config helpers ───────────────────────────────────────────────────


class TestConfigHelpers:
    def test_parse_apt_input(self):
        from linwin.shared.config import parse_apt_input
        assert parse_apt_input("nautilus, x11-apps, xfce4") == ["nautilus", "x11-apps", "xfce4"]

    def test_parse_apt_input_empty(self):
        from linwin.shared.config import parse_apt_input
        assert parse_apt_input("") == []

    def test_parse_apt_input_whitespace(self):
        from linwin.shared.config import parse_apt_input
        assert parse_apt_input("  ,  , a , ") == ["a"]

    def test_collect_app_selections(self):
        from linwin.shared.config import collect_app_selections
        mock_cb = MagicMock()
        mock_cb.value = True
        query_fn = MagicMock(return_value=mock_cb)
        apps = collect_app_selections(query_fn)
        assert len(apps) > 0

    def test_collect_app_selections_none_selected(self):
        from linwin.shared.config import collect_app_selections
        mock_cb = MagicMock()
        mock_cb.value = False
        query_fn = MagicMock(return_value=mock_cb)
        apps = collect_app_selections(query_fn)
        assert len(apps) == 0

    def test_load_save_config_injectable(self, tmp_path):
        """Config DB path can be injected for testing."""
        from linwin.shared.config import load_config, save_config
        db = tmp_path / "test.db"
        config = SetupConfig(distroName="Injected")
        save_config(config, db)
        loaded = load_config(db)
        assert loaded.distroName == "Injected"


# ── auto_config ──────────────────────────────────────────────────────


class TestAutoConfig:
    def test_parse_int(self):
        from linwin.windows.tasks.auto_config import _parse_int
        assert _parse_int("64 GB RAM") == 64
        assert _parse_int("no number") == 0
        assert _parse_int("", 42) == 42

    def test_build_auto_config(self):
        from linwin.windows.tasks.auto_config import build_auto_config, SystemProfile
        from linwin.windows.tasks.drive_scan import DriveCandidate
        from linwin.shared.config import SetupConfig as SC
        profile = SystemProfile(
            ram_gb=64, cpu_count=16,
            best_drive=DriveCandidate("D", 400, 1000, "SSD", "NVMe", ""),
            all_drives=[],
        )
        config = build_auto_config(profile, SC())
        assert config.wslDriveLetter == "D"
        assert config.wslconfig.memory == "16GB"  # 64/4
        assert config.wslconfig.processors == 8  # 16/2

    def test_build_auto_config_no_drive(self):
        from linwin.windows.tasks.auto_config import build_auto_config, SystemProfile
        from linwin.shared.config import SetupConfig as SC
        profile = SystemProfile(ram_gb=8, cpu_count=2, best_drive=None, all_drives=[])
        config = build_auto_config(profile, SC())
        assert config.wslDriveLetter == "C"
        assert config.wslconfig.memory == "4GB"  # min 4
        assert config.wslconfig.processors == 1  # min 1

    @pytest.mark.asyncio
    async def test_detect_system_profile(self):
        from linwin.windows.tasks.auto_config import detect_system_profile
        from linwin.shared.task_result import TaskResult
        from linwin.windows.tasks.drive_scan import DriveScanResult, DriveCandidate

        ram_result = TaskResult(ok=True, message="32 GB RAM")
        cpu_result = TaskResult(ok=True, message="8 logical processors")
        scan_result = DriveScanResult(candidates=[DriveCandidate("D", 400, 1000, "SSD", "NVMe", "")])

        with patch("linwin.windows.tasks.auto_config.validators.check_ram", new_callable=AsyncMock, return_value=ram_result), \
             patch("linwin.windows.tasks.auto_config.validators.check_cpu_count", new_callable=AsyncMock, return_value=cpu_result), \
             patch("linwin.windows.tasks.auto_config.scan_drives", new_callable=AsyncMock, return_value=scan_result):
            profile = await detect_system_profile()
            assert profile.ram_gb == 32
            assert profile.cpu_count == 8
            assert profile.best_drive.letter == "D"


# ── linux_invoke ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestLinuxInvoke:
    async def test_run_linux_headless(self):
        from linwin.windows.tasks.linux_invoke import run_linux_headless
        mock_result = _ok("LOG:hello")
        with patch("linwin.windows.tasks.linux_invoke.run_wsl", new_callable=AsyncMock, return_value=mock_result):
            result = await run_linux_headless(SetupConfig(), "enable-systemd", "C:\\project")
            assert result.success
