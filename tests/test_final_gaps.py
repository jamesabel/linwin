"""Final tests to push coverage above 80%."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linwin.shared.config import SetupConfig
from linwin.shared.subprocess_runner import SubprocessResult
from linwin.shared.task_result import TaskResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines())


# ── Linux Setup Screen (0% -> covered) ──────────────────────────────


@pytest.mark.asyncio
class TestLinuxSetupScreen:
    async def test_build_task_list(self):
        from linwin.linux.screens.setup import build_task_list
        from linwin.shared.config import AppEntry
        config = SetupConfig()
        config.enableSystemd = True
        config.aptPackages = ["nautilus", "xfce4"]
        config.optionalApps = [
            AppEntry("code", "VS Code", "code", "snap"),
            AppEntry("gedit", "Text Editor", "gedit", "apt"),
            AppEntry("matlab", "MATLAB", "matlab", "custom"),
        ]
        tasks = build_task_list(config)
        ids = [t[0] for t in tasks]
        assert "enable_systemd" in ids
        assert "apt_update" in ids
        assert "apt_nautilus" in ids
        assert "snap_code" in ids
        assert "apt_opt_gedit" in ids
        assert "verify_wslg" in ids
        # Custom apps should NOT have install tasks
        assert not any("matlab" in tid for tid in ids)

    async def test_build_task_list_no_systemd(self):
        from linwin.linux.screens.setup import build_task_list
        config = SetupConfig()
        config.enableSystemd = False
        config.aptPackages = []
        config.optionalApps = []
        tasks = build_task_list(config)
        ids = [t[0] for t in tasks]
        assert "enable_systemd" not in ids

    async def test_setup_screen_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.setup import SetupScreen

        config = SetupConfig()
        config.enableSystemd = True
        config.aptPackages = ["nautilus"]
        app = BaseSetupApp(config)

        # Mock all Linux tasks to succeed quickly
        with patch("linwin.linux.tasks.systemd.enable_systemd", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="enabled", needs_restart=True)), \
             patch("linwin.linux.tasks.apt.apt_update", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ok")), \
             patch("linwin.linux.tasks.apt.apt_upgrade", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ok")), \
             patch("linwin.linux.tasks.apt.install_apt_package", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="installed", skipped=True)), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", new_callable=AsyncMock, return_value=True), \
             patch("linwin.linux.tasks.snaps.ensure_snapd", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ready")), \
             patch("linwin.linux.tasks.wslg.verify_wslg", new_callable=AsyncMock,
                   return_value=MagicMock(display_set=True, display_value=":0", wslg_dir_exists=True, xeyes_works=True)):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = SetupScreen(config)
                app.push_screen(screen)
                await pilot.pause()

    async def test_setup_screen_systemd_skipped(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.setup import SetupScreen

        config = SetupConfig()
        config.enableSystemd = True
        config.aptPackages = []
        app = BaseSetupApp(config)

        with patch("linwin.linux.tasks.systemd.enable_systemd", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="already enabled", skipped=True)), \
             patch("linwin.linux.tasks.apt.apt_update", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ok")), \
             patch("linwin.linux.tasks.apt.apt_upgrade", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ok")), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.wslg.verify_wslg", new_callable=AsyncMock,
                   return_value=MagicMock(display_set=False, display_value="", wslg_dir_exists=False, xeyes_works=None)):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = SetupScreen(config)
                app.push_screen(screen)
                await pilot.pause()

    async def test_setup_screen_with_failed_apt(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.setup import SetupScreen

        config = SetupConfig()
        config.enableSystemd = False
        config.aptPackages = ["badpkg"]
        app = BaseSetupApp(config)

        with patch("linwin.linux.tasks.apt.apt_update", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ok")), \
             patch("linwin.linux.tasks.apt.apt_upgrade", new_callable=AsyncMock,
                   return_value=TaskResult(ok=False, message="fail")), \
             patch("linwin.linux.tasks.apt.install_apt_package", new_callable=AsyncMock,
                   return_value=TaskResult(ok=False, message="fail")), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", new_callable=AsyncMock, return_value=True), \
             patch("linwin.linux.tasks.snaps.ensure_snapd", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ready")), \
             patch("linwin.linux.tasks.wslg.verify_wslg", new_callable=AsyncMock,
                   return_value=MagicMock(display_set=True, display_value=":0", wslg_dir_exists=True, xeyes_works=False)):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = SetupScreen(config)
                app.push_screen(screen)
                await pilot.pause()

    async def test_setup_screen_with_snaps(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.setup import SetupScreen
        from linwin.shared.config import AppEntry

        config = SetupConfig()
        config.enableSystemd = False
        config.aptPackages = []
        config.optionalApps = [AppEntry("code", "VS Code", "code", "snap")]
        app = BaseSetupApp(config)

        with patch("linwin.linux.tasks.apt.apt_update", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ok")), \
             patch("linwin.linux.tasks.apt.apt_upgrade", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ok")), \
             patch("linwin.linux.tasks.snaps.check_systemd_running", new_callable=AsyncMock, return_value=True), \
             patch("linwin.linux.tasks.snaps.ensure_snapd", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="ready")), \
             patch("linwin.linux.tasks.snaps.install_snap", new_callable=AsyncMock,
                   return_value=TaskResult(ok=True, message="installed", skipped=True)), \
             patch("linwin.linux.tasks.wslg.verify_wslg", new_callable=AsyncMock,
                   return_value=MagicMock(display_set=True, display_value=":0", wslg_dir_exists=True, xeyes_works=None)):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = SetupScreen(config)
                app.push_screen(screen)
                await pilot.pause()


# ── Windows __main__ ─────────────────────────────────────────────────


class TestWindowsMainEntry:
    def test_main_starts_without_admin(self):
        """Test that main() proceeds without admin (no UAC gate)."""
        from linwin.windows.__main__ import main
        with patch("linwin.windows.app.check_admin", return_value=False), \
             patch("linwin.shared.config.load_config") as mock_load, \
             patch("linwin.windows.app.WindowsSetupApp") as MockApp:
            mock_load.return_value = SetupConfig()
            mock_app = MagicMock()
            MockApp.return_value = mock_app
            main()
            mock_app.run.assert_called_once()

    def test_main_admin_no_config(self, tmp_path, monkeypatch):
        from linwin.windows.__main__ import main
        with patch("linwin.windows.app.check_admin", return_value=True), \
             patch("linwin.shared.config.load_config", side_effect=FileNotFoundError), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


# ── Linux __main__ main() ───────────────────────────────────────────


class TestLinuxMainEntry:
    def test_main_interactive(self):
        """Test that main() in interactive mode creates and runs LinuxSetupApp."""
        from linwin.linux.__main__ import main
        with patch("sys.argv", ["linwin.linux"]), \
             patch("linwin.linux.__main__.find_config", return_value={"distroName": "Ubuntu-22.04"}), \
             patch("linwin.linux.app.LinuxSetupApp") as MockApp:
            mock_app = MagicMock()
            MockApp.return_value = mock_app
            main()
            mock_app.run.assert_called_once()

    def test_main_headless_enable_systemd(self):
        from linwin.linux.__main__ import main
        with patch("sys.argv", ["linwin.linux", "--headless", "--step", "enable-systemd"]), \
             patch("linwin.linux.__main__.find_config", return_value={}), \
             patch("linwin.linux.__main__.headless_enable_systemd", return_value=0), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_main_headless_install_packages(self):
        from linwin.linux.__main__ import main
        with patch("sys.argv", ["linwin.linux", "--headless", "--step", "install-packages"]), \
             patch("linwin.linux.__main__.find_config", return_value={}), \
             patch("linwin.linux.__main__.headless_install_packages", return_value=0), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_main_headless_configure_xrdp(self):
        from linwin.linux.__main__ import main
        with patch("sys.argv", ["linwin.linux", "--headless", "--step", "configure-xrdp"]), \
             patch("linwin.linux.__main__.find_config", return_value={}), \
             patch("linwin.linux.__main__.headless_configure_xrdp", return_value=0), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

    def test_main_headless_exception(self):
        from linwin.linux.__main__ import main
        with patch("sys.argv", ["linwin.linux", "--headless", "--step", "enable-systemd"]), \
             patch("linwin.linux.__main__.find_config", return_value={}), \
             patch("linwin.linux.__main__.headless_enable_systemd", side_effect=RuntimeError("boom")), \
             pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1


# ── Launcher remaining action methods ───────────────────────────────


@pytest.mark.asyncio
class TestLauncherRemainingActions:
    async def test_launcher_rdp_not_ready(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.launcher import LauncherScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        with patch("linwin.windows.screens.launcher.run_wsl", new_callable=AsyncMock, return_value=_fail()):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = LauncherScreen(config)
                app.push_screen(screen)
                await pilot.pause()
                screen._launch_rdp()
                await pilot.pause()

    async def test_launcher_rdp_ready(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.launcher import LauncherScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        with patch("linwin.windows.screens.launcher.run_wsl", new_callable=AsyncMock, return_value=_ok("active\nactive")), \
             patch("linwin.windows.screens.launcher.launch_rdp"):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = LauncherScreen(config)
                app.push_screen(screen)
                await pilot.pause()
                screen._launch_rdp()
                await pilot.pause()

    async def test_launcher_go_to_status(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.launcher import LauncherScreen
        from linwin.windows.tasks.health_check import HealthStatus

        config = SetupConfig()
        app = BaseSetupApp(config)
        health = HealthStatus(True, True, True, True)

        with patch("linwin.windows.screens.launcher.run_wsl", new_callable=AsyncMock, return_value=_ok("active")):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = LauncherScreen(config)
                app.push_screen(screen)
                await pilot.pause()

                with patch("linwin.windows.tasks.health_check.run_health_check", new_callable=AsyncMock, return_value=health), \
                     patch("linwin.windows.screens.status.validators.check_windows_build", new_callable=AsyncMock,
                           return_value=MagicMock(ok=True, message="22631", detail="")), \
                     patch("linwin.windows.screens.status.validators.check_virtualization", new_callable=AsyncMock,
                           return_value=MagicMock(ok=True, message="OK", detail="")), \
                     patch("linwin.windows.screens.status.validators.check_ram", new_callable=AsyncMock,
                           return_value=MagicMock(ok=True, message="64 GB", detail="")), \
                     patch("linwin.windows.screens.status.validators.check_cpu_count", new_callable=AsyncMock,
                           return_value=MagicMock(ok=True, message="16", detail="")), \
                     patch("linwin.windows.screens.status.validators.check_drive_exists", new_callable=AsyncMock,
                           return_value=MagicMock(ok=True, message="V:", detail="")):
                    screen._go_to_status()
                    await pilot.pause()


# ── Windows Verify Screen remaining ──────────────────────────────────


@pytest.mark.asyncio
class TestVerifyScreenRemaining:
    async def test_verify_with_failures(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.verify import VerifyScreen
        from linwin.windows.tasks.full_verify import VerifyResult, VerifyCheckItem

        config = SetupConfig()
        app = BaseSetupApp(config)

        mock_result = VerifyResult(checks=[
            VerifyCheckItem("WSL", False, category="windows"),
            VerifyCheckItem("systemd", False, category="linux"),
        ])

        with patch("linwin.windows.tasks.full_verify.run_full_verification",
                   new_callable=AsyncMock, return_value=mock_result):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = VerifyScreen(config)
                app.push_screen(screen)
                await pilot.pause()


# ── base_app copy log ────────────────────────────────────────────────


@pytest.mark.asyncio
class TestBaseAppActions:
    async def test_copy_log(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.shared.widgets import LogPanel
        from textual.screen import Screen

        class S(Screen):
            def compose(self):
                yield LogPanel(id="log")

        config = SetupConfig()

        class TestApp(BaseSetupApp):
            def on_mount(self):
                self.push_screen(S())

        app = TestApp(config)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            log = app.screen.query_one("#log", LogPanel)
            log.write_stdout("test content")
            app.action_copy_log()
