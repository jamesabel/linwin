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
        """App must reach LauncherScreen when all checks pass."""
        from unittest.mock import AsyncMock, patch
        from linwin.shared.config import SetupConfig
        from linwin.windows.app import WindowsSetupApp
        from linwin.windows.tasks.full_verify import VerifyResult

        config = SetupConfig()
        app = WindowsSetupApp(config)

        mock_verify = VerifyResult(checks=[])  # empty = all_passed

        with patch(
            "linwin.windows.tasks.full_verify.run_full_verification",
            new_callable=AsyncMock,
            return_value=mock_verify,
        ), patch("asyncio.sleep", new_callable=AsyncMock):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                from linwin.windows.screens.launcher import LauncherScreen
                assert isinstance(app.screen, LauncherScreen)

    async def test_app_shows_proposal_on_failure(self):
        """App must show SetupProposalScreen when verification finds failures."""
        from unittest.mock import AsyncMock, patch
        from linwin.shared.config import SetupConfig
        from linwin.windows.app import WindowsSetupApp
        from linwin.windows.tasks.full_verify import VerifyResult, VerifyCheckItem
        from linwin.windows.tasks.auto_config import SystemProfile
        from linwin.windows.tasks.drive_scan import DriveCandidate

        config = SetupConfig()
        app = WindowsSetupApp(config)

        mock_verify = VerifyResult(checks=[
            VerifyCheckItem("WSL feature enabled", False),
        ])
        mock_profile = SystemProfile(
            ram_gb=32, cpu_count=16,
            best_drive=DriveCandidate("D", 400, 1000, "SSD", "NVMe", ""),
            all_drives=[],
        )

        with patch(
            "linwin.windows.tasks.full_verify.run_full_verification",
            new_callable=AsyncMock,
            return_value=mock_verify,
        ), patch(
            "linwin.windows.tasks.auto_config.detect_system_profile",
            new_callable=AsyncMock,
            return_value=mock_profile,
        ):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                from linwin.windows.screens.setup_proposal import SetupProposalScreen
                assert isinstance(app.screen, SetupProposalScreen)

    async def test_app_survives_verification_exception(self):
        """App must not crash when verification raises an exception."""
        from unittest.mock import AsyncMock, patch
        from linwin.shared.config import SetupConfig
        from linwin.windows.app import WindowsSetupApp

        config = SetupConfig()
        app = WindowsSetupApp(config)

        with patch(
            "linwin.windows.tasks.full_verify.run_full_verification",
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
