"""Tests for Windows task modules: validators, wsl_install, wsl_config, features, health_check."""

from __future__ import annotations

import os
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from linwin.shared.subprocess_runner import SubprocessResult
from linwin.shared.task_result import TaskResult
from linwin.shared.config import SetupConfig


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "", stderr: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines(), stderr_lines=stderr.splitlines())


# ── validators ───────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestValidators:
    async def test_check_windows_build_ok(self):
        from linwin.windows.tasks.validators import check_windows_build
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok("22631")):
            result = await check_windows_build()
            assert result.ok
            assert "22631" in result.message

    async def test_check_windows_build_too_old(self):
        from linwin.windows.tasks.validators import check_windows_build
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok("18362")):
            result = await check_windows_build()
            assert not result.ok

    async def test_check_windows_build_failure(self):
        from linwin.windows.tasks.validators import check_windows_build
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_fail()):
            result = await check_windows_build()
            assert not result.ok

    async def test_check_windows_build_bad_output(self):
        from linwin.windows.tasks.validators import check_windows_build
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok("not-a-number")):
            result = await check_windows_build()
            assert not result.ok

    async def test_check_virtualization_enabled(self):
        from linwin.windows.tasks.validators import check_virtualization
        output = "FW=True\nMFR=GenuineIntel\nCPU=i9\nHYPERVISOR=True\nWSL=Enabled\nVMPLATFORM=Enabled\nHYPERV=Enabled"
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok(output)):
            result = await check_virtualization()
            assert result.ok

    async def test_check_virtualization_disabled_intel(self):
        from linwin.windows.tasks.validators import check_virtualization
        output = "FW=False\nMFR=GenuineIntel\nCPU=i9\nHYPERVISOR=False\nWSL=Disabled\nVMPLATFORM=Disabled\nHYPERV=Disabled"
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok(output)):
            result = await check_virtualization()
            assert not result.ok
            # The third positional arg is 'skipped' in TaskResult, but validators use it for detail text
            assert result.message == "Virtualization not enabled in BIOS/UEFI"

    async def test_check_virtualization_disabled_amd(self):
        from linwin.windows.tasks.validators import check_virtualization
        output = "FW=False\nMFR=AuthenticAMD\nCPU=Ryzen\nHYPERVISOR=False\nWSL=Disabled\nVMPLATFORM=Disabled\nHYPERV=Disabled"
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok(output)):
            result = await check_virtualization()
            assert not result.ok

    async def test_check_virtualization_failure(self):
        from linwin.windows.tasks.validators import check_virtualization
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_fail()):
            result = await check_virtualization()
            assert not result.ok

    async def test_check_drive_exists_ok(self):
        from linwin.windows.tasks.validators import check_drive_exists

        async def mock_ps(cmd, *args, **kwargs):
            if "Test-Path" in cmd:
                return _ok("True")
            if "Get-PSDrive" in cmd:
                return _ok("450.2")
            return _ok()

        with patch("linwin.windows.tasks.validators.run_powershell", side_effect=mock_ps):
            result = await check_drive_exists("V")
            assert result.ok

    async def test_check_drive_exists_missing(self):
        from linwin.windows.tasks.validators import check_drive_exists
        from linwin.windows.tasks.drive_scan import DriveScanResult, DriveCandidate

        async def mock_ps(cmd, *args, **kwargs):
            if "Test-Path" in cmd:
                return _ok("False")
            return _ok()

        scan_result = DriveScanResult(candidates=[DriveCandidate("D", 400, 1000, "SSD", "NVMe", "")])
        with patch("linwin.windows.tasks.validators.run_powershell", side_effect=mock_ps), \
             patch("linwin.windows.tasks.drive_scan.run_powershell", side_effect=mock_ps):
            result = await check_drive_exists("Z")
            assert not result.ok

    async def test_check_ram(self):
        from linwin.windows.tasks.validators import check_ram
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok("64")):
            result = await check_ram()
            assert result.ok
            assert "64" in result.message

    async def test_check_ram_failure(self):
        from linwin.windows.tasks.validators import check_ram
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_fail()):
            result = await check_ram()
            assert result.ok  # Still ok, just unknown

    async def test_check_cpu_count(self):
        from linwin.windows.tasks.validators import check_cpu_count
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_ok("16")):
            result = await check_cpu_count()
            assert result.ok
            assert "16" in result.message

    async def test_check_cpu_count_failure(self):
        from linwin.windows.tasks.validators import check_cpu_count
        with patch("linwin.windows.tasks.validators.run_powershell", new_callable=AsyncMock, return_value=_fail()):
            result = await check_cpu_count()
            assert result.ok  # Still ok, just unknown


# ── features ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestFeatures:
    async def test_check_feature_enabled(self):
        from linwin.windows.tasks.features import check_feature
        with patch("linwin.windows.tasks.features.run_powershell", new_callable=AsyncMock, return_value=_ok("Enabled")):
            assert await check_feature("VirtualMachinePlatform") is True

    async def test_check_feature_disabled(self):
        from linwin.windows.tasks.features import check_feature
        with patch("linwin.windows.tasks.features.run_powershell", new_callable=AsyncMock, return_value=_ok("Disabled")):
            assert await check_feature("VirtualMachinePlatform") is False

    async def test_check_feature_failure(self):
        from linwin.windows.tasks.features import check_feature
        with patch("linwin.windows.tasks.features.run_powershell", new_callable=AsyncMock, return_value=_fail()):
            assert await check_feature("VirtualMachinePlatform") is False

    async def test_enable_feature_already_enabled(self):
        from linwin.windows.tasks.features import enable_feature
        with patch("linwin.windows.tasks.features.check_feature", new_callable=AsyncMock, return_value=True):
            result = await enable_feature("VirtualMachinePlatform")
            assert result.ok
            assert result.already_enabled

    async def test_enable_feature_success(self):
        from linwin.windows.tasks.features import enable_feature
        with patch("linwin.windows.tasks.features.check_feature", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.features.run_powershell", new_callable=AsyncMock, return_value=_ok()):
            result = await enable_feature("VirtualMachinePlatform")
            assert result.ok
            assert result.enabled_now

    async def test_enable_feature_failure(self):
        from linwin.windows.tasks.features import enable_feature
        with patch("linwin.windows.tasks.features.check_feature", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.features.run_powershell", new_callable=AsyncMock, return_value=_fail("", "DISM error")):
            result = await enable_feature("VirtualMachinePlatform")
            assert not result.ok
            assert result.error

    async def test_enable_wsl_feature(self):
        from linwin.windows.tasks.features import enable_wsl_feature
        with patch("linwin.windows.tasks.features.enable_feature", new_callable=AsyncMock) as mock:
            await enable_wsl_feature()
            mock.assert_called_once()

    async def test_enable_vm_platform(self):
        from linwin.windows.tasks.features import enable_vm_platform
        with patch("linwin.windows.tasks.features.enable_feature", new_callable=AsyncMock) as mock:
            await enable_vm_platform()
            mock.assert_called_once()


# ── wsl_install ──────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWslInstall:
    async def test_update_wsl_success(self):
        from linwin.windows.tasks.wsl_install import update_wsl
        with patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_ok()):
            result = await update_wsl()
            assert result.ok

    async def test_update_wsl_failure(self):
        from linwin.windows.tasks.wsl_install import update_wsl
        with patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_fail()):
            result = await update_wsl()
            assert not result.ok

    async def test_set_wsl_default_version_success(self):
        from linwin.windows.tasks.wsl_install import set_wsl_default_version
        with patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_ok()):
            result = await set_wsl_default_version()
            assert result.ok

    async def test_set_wsl_default_version_failure(self):
        from linwin.windows.tasks.wsl_install import set_wsl_default_version
        with patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_fail()):
            result = await set_wsl_default_version()
            assert not result.ok

    async def test_get_registered_distros(self):
        from linwin.windows.tasks.wsl_install import get_registered_distros
        with patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock,
                   return_value=SubprocessResult(0, ["Ubuntu\x00", "Docker\x00"])):
            distros = await get_registered_distros()
            assert "Ubuntu" in distros
            assert "Docker" in distros

    async def test_get_registered_distros_failure(self):
        from linwin.windows.tasks.wsl_install import get_registered_distros
        with patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_fail()):
            distros = await get_registered_distros()
            assert distros == []

    async def test_is_distro_registered_true(self):
        from linwin.windows.tasks.wsl_install import is_distro_registered
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.get_registered_distros", new_callable=AsyncMock, return_value=["Ubuntu"]):
            assert await is_distro_registered(config) is True

    async def test_is_distro_registered_false(self):
        from linwin.windows.tasks.wsl_install import is_distro_registered
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.get_registered_distros", new_callable=AsyncMock, return_value=["Debian"]):
            assert await is_distro_registered(config) is False

    async def test_is_distro_on_target_drive(self, tmp_path):
        from linwin.windows.tasks.wsl_install import is_distro_on_target_drive
        config = SetupConfig(wslInstallPath=str(tmp_path))
        assert await is_distro_on_target_drive(config) is False
        (tmp_path / "ext4.vhdx").touch()
        assert await is_distro_on_target_drive(config) is True

    async def test_install_distro_already_registered(self):
        from linwin.windows.tasks.wsl_install import install_distro
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=True):
            result = await install_distro(config)
            assert result.ok
            assert result.skipped

    async def test_install_distro_success(self):
        from linwin.windows.tasks.wsl_install import install_distro
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_ok()):
            result = await install_distro(config)
            assert result.ok

    async def test_install_distro_failure(self):
        from linwin.windows.tasks.wsl_install import install_distro
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_fail()):
            result = await install_distro(config)
            assert not result.ok

    async def test_export_distro_already_on_target(self):
        from linwin.windows.tasks.wsl_install import export_distro
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.is_distro_on_target_drive", new_callable=AsyncMock, return_value=True):
            result, path = await export_distro(config)
            assert result.skipped

    async def test_export_distro_not_found(self):
        from linwin.windows.tasks.wsl_install import export_distro
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.is_distro_on_target_drive", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.wsl_install.get_registered_distros", new_callable=AsyncMock, return_value=[]):
            result, path = await export_distro(config)
            assert not result.ok

    async def test_export_distro_success(self):
        from linwin.windows.tasks.wsl_install import export_distro
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.is_distro_on_target_drive", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.wsl_install.get_registered_distros", new_callable=AsyncMock, return_value=["Ubuntu"]), \
             patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_ok()):
            result, path = await export_distro(config)
            assert result.ok
            assert path

    async def test_import_distro_already_on_target(self):
        from linwin.windows.tasks.wsl_install import import_distro
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.is_distro_on_target_drive", new_callable=AsyncMock, return_value=True):
            result = await import_distro(config, "/tmp/test.tar")
            assert result.skipped

    async def test_import_distro_success(self, tmp_path):
        from linwin.windows.tasks.wsl_install import import_distro
        config = SetupConfig(wslInstallPath=str(tmp_path / "wsl"))
        tar = tmp_path / "test.tar"
        tar.touch()
        with patch("linwin.windows.tasks.wsl_install.is_distro_on_target_drive", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.wsl_install.get_registered_distros", new_callable=AsyncMock, return_value=[]), \
             patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_ok()):
            result = await import_distro(config, str(tar))
            assert result.ok

    async def test_detect_default_user(self):
        from linwin.windows.tasks.wsl_install import detect_default_user
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.run_wsl", new_callable=AsyncMock,
                   return_value=SubprocessResult(0, ["james"])):
            user = await detect_default_user(config)
            assert user == "james"

    async def test_detect_default_user_none(self):
        from linwin.windows.tasks.wsl_install import detect_default_user
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.run_wsl", new_callable=AsyncMock,
                   return_value=SubprocessResult(0, [])):
            user = await detect_default_user(config)
            assert user is None

    async def test_set_default_user_already_set(self):
        from linwin.windows.tasks.wsl_install import set_default_user
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.run_wsl", new_callable=AsyncMock, return_value=_ok("yes")):
            result = await set_default_user(config, "james")
            assert result.skipped

    async def test_set_default_user_success(self):
        from linwin.windows.tasks.wsl_install import set_default_user
        config = SetupConfig()

        async def mock_wsl(distro, cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.windows.tasks.wsl_install.run_wsl", side_effect=mock_wsl):
            result = await set_default_user(config, "james")
            assert result.ok

    async def test_shutdown_wsl(self):
        from linwin.windows.tasks.wsl_install import shutdown_wsl
        with patch("linwin.windows.tasks.wsl_install.run_wsl_exec", new_callable=AsyncMock, return_value=_ok()):
            result = await shutdown_wsl()
            assert result.ok

    async def test_wait_for_wsl_ready_immediate(self):
        from linwin.windows.tasks.wsl_install import wait_for_wsl_ready
        config = SetupConfig()
        call_count = 0

        async def mock_wsl(distro, cmd, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "echo ready" in cmd:
                return _ok("ready")
            if "is-system-running" in cmd:
                return SubprocessResult(0, ["running", "active", "active"])
            return _ok()

        with patch("linwin.windows.tasks.wsl_install.run_wsl", side_effect=mock_wsl), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await wait_for_wsl_ready(config, max_attempts=2)
            assert result is True

    async def test_wait_for_wsl_ready_timeout(self):
        from linwin.windows.tasks.wsl_install import wait_for_wsl_ready
        config = SetupConfig()
        with patch("linwin.windows.tasks.wsl_install.run_wsl", new_callable=AsyncMock, return_value=_fail()), \
             patch("asyncio.sleep", new_callable=AsyncMock):
            result = await wait_for_wsl_ready(config, max_attempts=1)
            assert result is False


# ── wsl_config ───────────────────────────────────────────────────────


class TestWslConfig:
    def test_generate_content(self):
        from linwin.windows.tasks.wsl_config import generate_wslconfig_content
        config = SetupConfig()
        content = generate_wslconfig_content(config)
        assert "memory" in content
        assert "processors" in content
        assert "guiapplications" in content.lower()

    def test_get_wslconfig_path(self):
        from linwin.windows.tasks.wsl_config import get_wslconfig_path
        path = get_wslconfig_path()
        assert ".wslconfig" in path

    def test_check_wslconfig_exists_no(self, tmp_path, monkeypatch):
        from linwin.windows.tasks.wsl_config import check_wslconfig_exists
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        exists, content = check_wslconfig_exists()
        assert not exists
        assert content == ""

    def test_check_wslconfig_exists_yes(self, tmp_path, monkeypatch):
        from linwin.windows.tasks.wsl_config import check_wslconfig_exists
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        (tmp_path / ".wslconfig").write_text("[wsl2]\nmemory=8GB\n")
        exists, content = check_wslconfig_exists()
        assert exists
        assert "memory" in content

    def test_write_wslconfig_new(self, tmp_path, monkeypatch):
        from linwin.windows.tasks.wsl_config import write_wslconfig
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        config = SetupConfig()
        config.wslconfig.swapFile = str(tmp_path / "swap.vhdx")
        result = write_wslconfig(config, overwrite=True)
        assert result.ok
        assert (tmp_path / ".wslconfig").exists()

    def test_write_wslconfig_exists_no_overwrite(self, tmp_path, monkeypatch):
        from linwin.windows.tasks.wsl_config import write_wslconfig
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        (tmp_path / ".wslconfig").write_text("old content")
        config = SetupConfig()
        result = write_wslconfig(config, overwrite=False)
        assert not result.ok
        assert result.existing_content == "old content"


# ── health_check ─────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestHealthCheck:
    async def test_run_health_check_all_pass(self):
        from linwin.windows.tasks.health_check import run_health_check
        config = SetupConfig()
        with patch("linwin.windows.tasks.health_check.features.check_feature", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.health_check.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=True), \
             patch("linwin.windows.tasks.health_check.wsl_install.is_distro_on_target_drive", new_callable=AsyncMock, return_value=True):
            health = await run_health_check(config)
            assert health.ready
            assert health.wsl_feature
            assert health.vm_platform
            assert health.distro_registered
            assert health.vhd_on_target
            lines = health.summary_lines
            assert len(lines) == 4
            assert all(passed for _, passed in lines)

    async def test_run_health_check_not_ready(self):
        from linwin.windows.tasks.health_check import run_health_check
        config = SetupConfig()
        with patch("linwin.windows.tasks.health_check.features.check_feature", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.health_check.wsl_install.is_distro_registered", new_callable=AsyncMock, return_value=False), \
             patch("linwin.windows.tasks.health_check.wsl_install.is_distro_on_target_drive", new_callable=AsyncMock, return_value=False):
            health = await run_health_check(config)
            assert not health.ready
