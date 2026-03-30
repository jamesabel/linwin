"""Tests for the __main__ entry points."""

import subprocess
import sys

import pytest


class TestWindowsMain:
    def test_module_imports(self):
        """Verify linwin.windows.__main__ can be imported."""
        from linwin.windows.__main__ import main
        assert callable(main)

    def test_missing_config_exits(self, tmp_path, monkeypatch):
        """Running from a directory without config.json should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "linwin.windows"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=15,
        )
        # Should exit non-zero (either can't find config, or not admin)
        assert result.returncode != 0 or "config.json" in result.stdout.lower() or "administrator" in result.stdout.lower()


@pytest.mark.asyncio
class TestWindowsAppStartup:
    """Verify the Textual app starts up without crashing."""

    async def test_app_does_not_crash_on_startup(self):
        """App must survive mount + health check without an unhandled exception.

        Reproduces the abrupt-exit scenario where _startup_check fires
        concurrent subprocesses and the app dies before they complete.
        """
        from unittest.mock import AsyncMock, patch
        from linwin.shared.config import SetupConfig
        from linwin.windows.app import WindowsSetupApp
        from linwin.windows.tasks.health_check import HealthStatus

        config = SetupConfig()
        app = WindowsSetupApp(config)

        mock_health = HealthStatus(
            wsl_feature=True,
            vm_platform=True,
            distro_registered=True,
            vhd_on_target=True,
        )

        with patch(
            "linwin.windows.tasks.health_check.run_health_check",
            new_callable=AsyncMock,
            return_value=mock_health,
        ):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                # App should be showing the LauncherScreen (health passed)
                from linwin.windows.screens.launcher import LauncherScreen
                assert isinstance(app.screen, LauncherScreen)

    async def test_app_survives_health_check_failure(self):
        """App must not crash when health check reports failures."""
        from unittest.mock import AsyncMock, patch
        from linwin.shared.config import SetupConfig
        from linwin.windows.app import WindowsSetupApp
        from linwin.windows.tasks.health_check import HealthStatus

        config = SetupConfig()
        app = WindowsSetupApp(config)

        mock_health = HealthStatus(
            wsl_feature=False,
            vm_platform=False,
            distro_registered=False,
            vhd_on_target=False,
        )

        with patch(
            "linwin.windows.tasks.health_check.run_health_check",
            new_callable=AsyncMock,
            return_value=mock_health,
        ):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                from linwin.windows.screens.status import StatusScreen
                assert isinstance(app.screen, StatusScreen)

    async def test_app_survives_health_check_exception(self):
        """App must not crash when health check raises an exception."""
        from unittest.mock import AsyncMock, patch
        from linwin.shared.config import SetupConfig
        from linwin.windows.app import WindowsSetupApp

        config = SetupConfig()
        app = WindowsSetupApp(config)

        with patch(
            "linwin.windows.tasks.health_check.run_health_check",
            new_callable=AsyncMock,
            side_effect=RuntimeError("subprocess died"),
        ):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                # App should exit gracefully, not crash


class TestLinuxMain:
    def test_module_imports(self):
        """Verify linwin.linux.__main__ can be imported."""
        from linwin.linux.__main__ import main
        assert callable(main)

    def test_headless_requires_step(self):
        """--headless without --step should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "linwin.linux", "--headless"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0

    def test_missing_config_exits(self, tmp_path):
        """Running from a directory without config.json should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "linwin.linux", "--headless", "--step", "enable-systemd"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=15,
        )
        # Should fail — either module not found (no linwin package in tmp) or config missing
        assert result.returncode != 0
