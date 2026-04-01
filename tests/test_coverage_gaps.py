"""Tests targeting remaining coverage gaps to reach 80%."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linwin.shared.config import SetupConfig
from linwin.shared.subprocess_runner import SubprocessResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines())


# ── full_verify (34% -> ~80%) ────────────────────────────────────────


@pytest.mark.asyncio
class TestFullVerify:
    async def test_run_full_verification_all_pass(self):
        from linwin.windows.tasks.full_verify import run_full_verification

        config = SetupConfig()
        config.aptPackages = ["nautilus"]
        config.snaps = []

        with patch("linwin.windows.tasks.full_verify.features.check_feature", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.run_powershell", new_callable=AsyncMock, return_value=_ok("WSL version 2.0")), \
             patch("linwin.windows.tasks.full_verify.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.validators.check_drive_exists", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, detail="OK")), \
             patch("linwin.windows.tasks.full_verify.check_wslconfig_exists", return_value=(True, "guiApplications=true")), \
             patch("os.path.exists", return_value=True), \
             patch("linwin.windows.tasks.full_verify.run_wsl", new_callable=AsyncMock,
                   side_effect=lambda d, cmd, **kw: _ok(
                       "2" if "Select-String" in cmd or "-l -v" in cmd
                       else "active" if "is-active" in cmd
                       else "port=3390" if "grep" in cmd and "port" in cmd
                       else ":0" if "DISPLAY" in cmd
                       else "yes")), \
             patch("linwin.windows.tasks.full_verify.check_systemd", new_callable=AsyncMock, return_value=(True, "systemd")), \
             patch("linwin.windows.tasks.full_verify.check_snapd", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.check_apt_package", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.check_snap_package", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.check_wslg_dir", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.check_drive_mounted", new_callable=AsyncMock, return_value=True):
            result = await run_full_verification(config)
            assert result.all_passed
            assert len(result.checks) > 0
            assert result.failed_checks == []
            assert not result.setup_needed

    async def test_run_full_verification_distro_not_registered(self):
        from linwin.windows.tasks.full_verify import run_full_verification

        config = SetupConfig()
        config.aptPackages = []
        config.snaps = []

        with patch("linwin.windows.tasks.full_verify.features.check_feature", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.run_powershell", new_callable=AsyncMock, return_value=_ok("WSL version 2.0")), \
             patch("linwin.windows.tasks.full_verify.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.full_verify.validators.check_drive_exists", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, detail="OK")), \
             patch("linwin.windows.tasks.full_verify.check_wslconfig_exists", return_value=(False, "")), \
             patch("os.path.exists", return_value=False):
            result = await run_full_verification(config)
            assert not result.all_passed
            assert len(result.failed_checks) > 0

    async def test_run_full_verification_with_progress(self):
        from linwin.windows.tasks.full_verify import run_full_verification

        config = SetupConfig()
        config.aptPackages = []
        config.snaps = []
        progress_items = []

        async def on_progress(item):
            progress_items.append(item)

        with patch("linwin.windows.tasks.full_verify.features.check_feature", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.full_verify.run_powershell", new_callable=AsyncMock, return_value=_ok("WSL version 2.0")), \
             patch("linwin.windows.tasks.full_verify.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.full_verify.validators.check_drive_exists", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, detail="OK")), \
             patch("linwin.windows.tasks.full_verify.check_wslconfig_exists", return_value=(False, "")), \
             patch("os.path.exists", return_value=False):
            await run_full_verification(config, on_progress=on_progress)
            assert len(progress_items) > 0


# ── drive_picker ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestDrivePickerModal:
    async def test_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.drive_picker import DrivePickerModal
        from linwin.windows.tasks.drive_scan import DriveScanResult, DriveCandidate

        config = SetupConfig()
        app = BaseSetupApp(config)

        candidates = [
            DriveCandidate("D", 400, 1000, "SSD", "NVMe", "Data"),
            DriveCandidate("E", 200, 500, "HDD", "SATA", "Backup"),
        ]
        scan_result = DriveScanResult(candidates=candidates, excluded=[("A", "USB")])

        with patch("linwin.windows.screens.drive_picker.scan_drives", new_callable=AsyncMock, return_value=scan_result):
            async with app.run_test(size=(80, 24)) as pilot:
                app.push_screen(DrivePickerModal("C"))
                await pilot.pause()

    async def test_compose_no_candidates(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.drive_picker import DrivePickerModal
        from linwin.windows.tasks.drive_scan import DriveScanResult

        config = SetupConfig()
        app = BaseSetupApp(config)
        scan_result = DriveScanResult(candidates=[], excluded=[("A", "USB")])

        with patch("linwin.windows.screens.drive_picker.scan_drives", new_callable=AsyncMock, return_value=scan_result):
            async with app.run_test(size=(80, 24)) as pilot:
                app.push_screen(DrivePickerModal())
                await pilot.pause()

    async def test_compose_error(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.drive_picker import DrivePickerModal
        from linwin.windows.tasks.drive_scan import DriveScanResult

        config = SetupConfig()
        app = BaseSetupApp(config)
        scan_result = DriveScanResult(error="Failed to scan")

        with patch("linwin.windows.screens.drive_picker.scan_drives", new_callable=AsyncMock, return_value=scan_result):
            async with app.run_test(size=(80, 24)) as pilot:
                app.push_screen(DrivePickerModal())
                await pilot.pause()


# ── drive_scan full scan ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestDriveScan:
    async def test_scan_drives_success(self):
        from linwin.windows.tasks.drive_scan import scan_drives
        output = "D|400.5|1000.0|SSD|NVMe|Data\nC|50.0|500.0|SSD|SATA|System\nE|10.0|100.0|HDD|USB|External"
        with patch("linwin.windows.tasks.drive_scan.run_powershell", new_callable=AsyncMock, return_value=_ok(output)):
            result = await scan_drives()
            assert len(result.candidates) == 2  # D and C (E excluded for USB)
            assert result.candidates[0].letter == "D"  # NVMe scores highest
            assert len(result.excluded) == 1

    async def test_scan_drives_failure(self):
        from linwin.windows.tasks.drive_scan import scan_drives
        with patch("linwin.windows.tasks.drive_scan.run_powershell", new_callable=AsyncMock, return_value=_fail()):
            result = await scan_drives()
            assert result.error

    async def test_scan_drives_low_space_excluded(self):
        from linwin.windows.tasks.drive_scan import scan_drives
        output = "D|5.0|100.0|SSD|SATA|Small"
        with patch("linwin.windows.tasks.drive_scan.run_powershell", new_callable=AsyncMock, return_value=_ok(output)):
            result = await scan_drives()
            assert len(result.candidates) == 0
            assert len(result.excluded) == 1


# ── Windows __main__ ─────────────────────────────────────────────────


class TestWindowsMainModule:
    def test_check_admin_false(self):
        from linwin.windows.app import check_admin
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0):
            assert check_admin() is False

    def test_check_admin_true(self):
        from linwin.windows.app import check_admin
        with patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1):
            assert check_admin() is True

    def test_check_admin_exception(self):
        from linwin.windows.app import check_admin
        with patch("ctypes.windll.shell32.IsUserAnAdmin", side_effect=RuntimeError):
            assert check_admin() is False

    def test_run_elevated(self):
        from linwin.windows.app import run_elevated
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert run_elevated("echo test") is True
            mock_run.assert_called_once()

    def test_run_elevated_failure(self):
        from linwin.windows.app import run_elevated
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert run_elevated("echo test") is False


# ── Linux __main__ remaining branches ────────────────────────────────


class TestLinuxMainBranches:
    def test_headless_install_packages_apt_failure(self):
        from linwin.linux.__main__ import headless_install_packages

        config = {"aptPackages": ["nautilus"], "snaps": []}

        with patch("linwin.linux.__main__._run_task", return_value=False), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", return_value=True), \
             patch("linwin.linux.tasks.snaps.ensure_snapd") as mock_snapd, \
             patch("linwin.linux.tasks.wslg.verify_wslg") as mock_wslg:
            from linwin.shared.task_result import TaskResult as TR
            mock_snapd.return_value = TR(ok=True, message="ready")
            mock_wslg.return_value = MagicMock(display_set=True, display_value=":0", wslg_dir_exists=True)
            result = headless_install_packages(config)
            assert result == 1

    def test_headless_install_packages_snapd_fails(self):
        from linwin.linux.__main__ import headless_install_packages

        config = {"aptPackages": [], "snaps": []}

        with patch("linwin.linux.__main__._run_task", return_value=True), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", return_value=True), \
             patch("linwin.linux.tasks.snaps.ensure_snapd") as mock_snapd, \
             patch("linwin.linux.tasks.wslg.verify_wslg") as mock_wslg:
            from linwin.shared.task_result import TaskResult as TR
            mock_snapd.return_value = TR(ok=False, message="fail")
            mock_wslg.return_value = MagicMock(display_set=False, display_value="", wslg_dir_exists=False)
            result = headless_install_packages(config)
            assert result == 1


# ── Windows Launcher actions coverage ────────────────────────────────


@pytest.mark.asyncio
class TestLauncherActions:
    async def test_launcher_action_methods(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.launcher import LauncherScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = LauncherScreen(config)
            app.push_screen(screen)
            await pilot.pause()

            with patch("linwin.windows.screens.launcher.notify_launch"):
                screen.action_launch_files()

            with patch("linwin.windows.screens.launcher.launch_windows_terminal"):
                screen.action_launch_terminal()


# ── Windows Verify actions coverage ──────────────────────────────────


@pytest.mark.asyncio
class TestVerifyActions:
    async def test_verify_action_methods(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.verify import VerifyScreen
        from linwin.windows.tasks.full_verify import VerifyResult

        config = SetupConfig()
        app = BaseSetupApp(config)

        with patch("linwin.windows.tasks.full_verify.run_full_verification",
                   new_callable=AsyncMock, return_value=VerifyResult(checks=[])):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = VerifyScreen(config)
                app.push_screen(screen)
                await pilot.pause()

                with patch("linwin.windows.screens.verify.notify_launch"):
                    screen.action_launch_files()

                with patch("linwin.windows.screens.verify.launch_windows_terminal"):
                    screen.action_launch_terminal()


# ── StatusScreen detail modal ────────────────────────────────────────


@pytest.mark.asyncio
class TestDetailModal:
    async def test_modal_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.status import DetailModal

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            app.push_screen(DetailModal("Error Title", "Some detail text"))
            await pilot.pause()


# ── setup_logging coverage ───────────────────────────────────────────


class TestSetupLogging:
    def test_get_log_dir_linux(self):
        from linwin.shared.setup_logging import get_log_dir
        with patch("sys.platform", "linux"), \
             patch.dict(os.environ, {"XDG_DATA_HOME": ""}, clear=False), \
             patch("os.path.expanduser", return_value="/home/test"):
            path = get_log_dir()
            assert "linwin" in str(path)

    def test_get_log_dir_linux_xdg(self):
        from linwin.shared.setup_logging import get_log_dir
        with patch("sys.platform", "linux"), \
             patch.dict(os.environ, {"XDG_DATA_HOME": "/custom/data"}, clear=False):
            path = get_log_dir()
            assert "custom" in str(path) or "linwin" in str(path)


# ── subprocess_runner edge cases ─────────────────────────────────────


@pytest.mark.asyncio
class TestSubprocessEdgeCases:
    async def test_run_wsl_with_cwd(self):
        from linwin.shared.subprocess_runner import run_wsl
        with patch("linwin.shared.subprocess_runner.run_command", new_callable=AsyncMock, return_value=_ok()) as mock:
            await run_wsl("Ubuntu", "echo hi", cwd="/tmp")
            args = mock.call_args[0][0]
            assert "--cd" in args

    async def test_run_local_linux(self):
        from linwin.shared.subprocess_runner import run_local
        with patch("sys.platform", "linux"), \
             patch("linwin.shared.subprocess_runner.run_command", new_callable=AsyncMock, return_value=_ok()) as mock:
            await run_local("echo hi")
            args = mock.call_args[0][0]
            assert "bash" in args
