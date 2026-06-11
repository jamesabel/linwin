"""Tests for Linux task modules: apt, snaps, systemd, wslg, xrdp."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from linwin.shared.subprocess_runner import SubprocessResult
from linwin.shared.task_result import TaskResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


def _fail(output: str = "", stderr: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=1, stdout_lines=output.splitlines(), stderr_lines=stderr.splitlines())


# ── apt ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestApt:
    async def test_apt_update_success(self):
        from linwin.linux.tasks.apt import apt_update
        with patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_ok()):
            result = await apt_update()
            assert result.ok

    async def test_apt_update_failure(self):
        from linwin.linux.tasks.apt import apt_update
        with patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_fail()):
            result = await apt_update()
            assert not result.ok

    async def test_apt_upgrade_success(self):
        from linwin.linux.tasks.apt import apt_upgrade
        with patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_ok()):
            result = await apt_upgrade()
            assert result.ok

    async def test_apt_upgrade_failure(self):
        from linwin.linux.tasks.apt import apt_upgrade
        with patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_fail()):
            result = await apt_upgrade()
            assert not result.ok

    async def test_is_apt_installed_true(self):
        from linwin.linux.tasks.apt import is_apt_installed
        with patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_ok("yes")):
            assert await is_apt_installed("nautilus") is True

    async def test_is_apt_installed_false(self):
        from linwin.linux.tasks.apt import is_apt_installed
        with patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_ok("no")):
            assert await is_apt_installed("nautilus") is False

    async def test_install_already_installed(self):
        from linwin.linux.tasks.apt import install_apt_package
        with patch("linwin.linux.tasks.apt.is_apt_installed", new_callable=AsyncMock, return_value=True):
            result = await install_apt_package("nautilus")
            assert result.ok
            assert result.skipped

    async def test_install_new_package_success(self):
        from linwin.linux.tasks.apt import install_apt_package
        with patch("linwin.linux.tasks.apt.is_apt_installed", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_ok()):
            result = await install_apt_package("nautilus")
            assert result.ok
            assert not result.skipped

    async def test_install_new_package_failure(self):
        from linwin.linux.tasks.apt import install_apt_package
        with patch("linwin.linux.tasks.apt.is_apt_installed", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.apt.run_local", new_callable=AsyncMock, return_value=_fail()):
            result = await install_apt_package("nautilus")
            assert not result.ok


# ── snaps ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSnaps:
    async def test_check_systemd_running_true(self):
        from linwin.linux.tasks.snaps import check_systemd_running
        with patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_ok("running")):
            assert await check_systemd_running() is True

    async def test_check_systemd_running_degraded(self):
        from linwin.linux.tasks.snaps import check_systemd_running
        with patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_ok("degraded")):
            assert await check_systemd_running() is True

    async def test_check_systemd_running_false(self):
        from linwin.linux.tasks.snaps import check_systemd_running
        with patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_ok("starting")):
            assert await check_systemd_running() is False

    async def test_ensure_snapd_already_installed(self):
        from linwin.linux.tasks.snaps import ensure_snapd
        with patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_ok("yes")):
            result = await ensure_snapd()
            assert result.ok

    async def test_ensure_snapd_needs_install(self):
        from linwin.linux.tasks.snaps import ensure_snapd
        call_count = 0

        async def mock_run(cmd, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            if "command -v snap" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.linux.tasks.snaps.run_local", side_effect=mock_run):
            result = await ensure_snapd()
            assert result.ok

    async def test_ensure_snapd_install_fails(self):
        from linwin.linux.tasks.snaps import ensure_snapd

        async def mock_run(cmd, *args, **kwargs):
            if "command -v snap" in cmd:
                return _ok("no")
            if "apt install" in cmd:
                return _fail()
            return _ok()

        with patch("linwin.linux.tasks.snaps.run_local", side_effect=mock_run):
            result = await ensure_snapd()
            assert not result.ok

    async def test_is_snap_installed_true(self):
        from linwin.linux.tasks.snaps import is_snap_installed
        with patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_ok("code 1.80 yes")):
            assert await is_snap_installed("code") is True

    async def test_is_snap_installed_false(self):
        from linwin.linux.tasks.snaps import is_snap_installed
        with patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_ok("no")):
            assert await is_snap_installed("code") is False

    async def test_install_snap_already_installed(self):
        from linwin.linux.tasks.snaps import install_snap
        from linwin.shared.config import SnapPackage
        snap = SnapPackage("code", classic=True)
        with patch("linwin.linux.tasks.snaps.is_snap_installed", new_callable=AsyncMock, return_value=True):
            result = await install_snap(snap)
            assert result.ok
            assert result.skipped

    async def test_install_snap_success(self):
        from linwin.linux.tasks.snaps import install_snap
        from linwin.shared.config import SnapPackage
        snap = SnapPackage("code", classic=True)
        with patch("linwin.linux.tasks.snaps.is_snap_installed", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_ok()):
            result = await install_snap(snap)
            assert result.ok

    async def test_install_snap_failure(self):
        from linwin.linux.tasks.snaps import install_snap
        from linwin.shared.config import SnapPackage
        snap = SnapPackage("code", classic=True)
        with patch("linwin.linux.tasks.snaps.is_snap_installed", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.snaps.run_local", new_callable=AsyncMock, return_value=_fail()):
            result = await install_snap(snap)
            assert not result.ok

    async def test_install_snap_non_classic(self):
        from linwin.linux.tasks.snaps import install_snap
        from linwin.shared.config import SnapPackage
        snap = SnapPackage("hello", classic=False)
        mock = AsyncMock(return_value=_ok())
        with patch("linwin.linux.tasks.snaps.is_snap_installed", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.snaps.run_local", mock):
            result = await install_snap(snap)
            assert result.ok
            # Should NOT contain --classic
            call_cmd = mock.call_args[0][0]
            assert "--classic" not in call_cmd


# ── systemd ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestSystemd:
    async def test_check_enabled_true(self):
        from linwin.linux.tasks.systemd import check_systemd_enabled
        with patch("linwin.linux.tasks.systemd.run_local", new_callable=AsyncMock, return_value=_ok("yes")):
            assert await check_systemd_enabled() is True

    async def test_check_enabled_false(self):
        from linwin.linux.tasks.systemd import check_systemd_enabled
        with patch("linwin.linux.tasks.systemd.run_local", new_callable=AsyncMock, return_value=_ok("no")):
            assert await check_systemd_enabled() is False

    async def test_check_running_true(self):
        from linwin.linux.tasks.systemd import check_systemd_running
        with patch("linwin.linux.tasks.systemd.run_local", new_callable=AsyncMock, return_value=_ok("systemd")):
            assert await check_systemd_running() is True

    async def test_check_running_false(self):
        from linwin.linux.tasks.systemd import check_systemd_running
        with patch("linwin.linux.tasks.systemd.run_local", new_callable=AsyncMock, return_value=_ok("init")):
            assert await check_systemd_running() is False

    async def test_enable_already_enabled(self):
        from linwin.linux.tasks.systemd import enable_systemd
        with patch("linwin.linux.tasks.systemd.check_systemd_enabled", new_callable=AsyncMock, return_value=True):
            result = await enable_systemd()
            assert result.ok
            assert result.skipped

    async def test_enable_with_boot_section(self):
        from linwin.linux.tasks.systemd import enable_systemd

        async def mock_run(cmd, *args, **kwargs):
            if "boot" in cmd:
                return _ok("yes")
            return _ok()

        with patch("linwin.linux.tasks.systemd.check_systemd_enabled", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.systemd.run_local", side_effect=mock_run):
            result = await enable_systemd()
            assert result.ok
            assert result.needs_restart

    async def test_enable_without_boot_section(self):
        from linwin.linux.tasks.systemd import enable_systemd

        async def mock_run(cmd, *args, **kwargs):
            if "boot" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.linux.tasks.systemd.check_systemd_enabled", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.systemd.run_local", side_effect=mock_run):
            result = await enable_systemd()
            assert result.ok

    async def test_enable_failure(self):
        from linwin.linux.tasks.systemd import enable_systemd
        calls = []

        async def mock_run(cmd, *args, **kwargs):
            calls.append(cmd)
            if cmd.startswith("grep"):
                return _ok("no")  # no [boot] section
            # The tee command to write wsl.conf fails
            return _fail()

        with patch("linwin.linux.tasks.systemd.check_systemd_enabled", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.systemd.run_local", side_effect=mock_run):
            result = await enable_systemd()
            assert not result.ok


# ── wslg ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestWslg:
    async def test_verify_wslg_all_good(self):
        from linwin.linux.tasks.wslg import verify_wslg
        with patch("linwin.linux.tasks.wslg.run_local", new_callable=AsyncMock, return_value=_ok("yes")), \
             patch.dict("os.environ", {"DISPLAY": ":0"}):
            result = await verify_wslg()
            assert result.display_set
            assert result.display_value == ":0"
            assert result.wslg_dir_exists

    async def test_verify_wslg_no_display(self):
        from linwin.linux.tasks.wslg import verify_wslg
        with patch("linwin.linux.tasks.wslg.run_local", new_callable=AsyncMock, return_value=_ok("yes")), \
             patch.dict("os.environ", {}, clear=True):
            result = await verify_wslg()
            assert not result.display_set

    async def test_verify_wslg_no_dir(self):
        from linwin.linux.tasks.wslg import verify_wslg

        async def mock_run(cmd, *args, **kwargs):
            if "/mnt/wslg" in cmd:
                return _ok("no")
            if "command -v xeyes" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.linux.tasks.wslg.run_local", side_effect=mock_run), \
             patch.dict("os.environ", {"DISPLAY": ":0"}):
            result = await verify_wslg()
            assert not result.wslg_dir_exists

    async def test_verify_wslg_xeyes_works(self):
        from linwin.linux.tasks.wslg import verify_wslg

        async def mock_run(cmd, *args, **kwargs):
            if "command -v xeyes" in cmd:
                return _ok("yes")
            if "xeyes" in cmd and "XPID" in cmd:
                return _ok("running")
            return _ok("yes")

        with patch("linwin.linux.tasks.wslg.run_local", side_effect=mock_run), \
             patch.dict("os.environ", {"DISPLAY": ":0"}):
            result = await verify_wslg()
            assert result.xeyes_works is True

    async def test_verify_wslg_xeyes_fails(self):
        from linwin.linux.tasks.wslg import verify_wslg

        async def mock_run(cmd, *args, **kwargs):
            if "command -v xeyes" in cmd:
                return _ok("yes")
            if "xeyes" in cmd and "XPID" in cmd:
                return _ok("stopped")
            return _ok("yes")

        with patch("linwin.linux.tasks.wslg.run_local", side_effect=mock_run), \
             patch.dict("os.environ", {"DISPLAY": ":0"}):
            result = await verify_wslg()
            assert result.xeyes_works is False


# ── xrdp ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestXrdp:
    async def test_is_xrdp_installed(self):
        from linwin.linux.tasks.xrdp import is_xrdp_installed
        with patch("linwin.linux.tasks.xrdp.is_apt_installed", new_callable=AsyncMock, return_value=True):
            assert await is_xrdp_installed() is True

    async def test_install_xrdp_all_installed(self):
        from linwin.linux.tasks.xrdp import install_xrdp
        with patch("linwin.linux.tasks.xrdp.is_apt_installed", new_callable=AsyncMock, return_value=True):
            result = await install_xrdp()
            assert result.ok
            assert result.skipped

    async def test_install_xrdp_needs_install(self):
        from linwin.linux.tasks.xrdp import install_xrdp
        with patch("linwin.linux.tasks.xrdp.is_apt_installed", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok()):
            result = await install_xrdp()
            assert result.ok

    async def test_install_xrdp_failure(self):
        from linwin.linux.tasks.xrdp import install_xrdp
        with patch("linwin.linux.tasks.xrdp.is_apt_installed", new_callable=AsyncMock, return_value=False), \
             patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_fail()):
            result = await install_xrdp()
            assert not result.ok

    async def test_configure_port_already_set(self):
        from linwin.linux.tasks.xrdp import configure_xrdp_port
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("port=3390")):
            result = await configure_xrdp_port(3390)
            assert result.ok
            assert result.skipped

    async def test_configure_port_needs_change(self):
        from linwin.linux.tasks.xrdp import configure_xrdp_port

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("port=3389")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_xrdp_port(3390)
            assert result.ok

    async def test_configure_port_failure(self):
        from linwin.linux.tasks.xrdp import configure_xrdp_port

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("port=3389")
            return _fail()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_xrdp_port(3390)
            assert not result.ok

    async def test_configure_session_already_done(self):
        from linwin.linux.tasks.xrdp import configure_xrdp_session
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("yes")):
            result = await configure_xrdp_session()
            assert result.ok
            assert result.skipped

    async def test_configure_session_success(self):
        from linwin.linux.tasks.xrdp import configure_xrdp_session

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_xrdp_session()
            assert result.ok

    async def test_configure_session_failure(self):
        from linwin.linux.tasks.xrdp import configure_xrdp_session

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("no")
            if "tee" in cmd:
                return _fail()
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_xrdp_session()
            assert not result.ok

    async def test_configure_colord_polkit_already_present(self):
        from linwin.linux.tasks.xrdp import configure_colord_polkit
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("yes")):
            result = await configure_colord_polkit()
            assert result.skipped

    async def test_configure_colord_polkit_success(self):
        from linwin.linux.tasks.xrdp import configure_colord_polkit

        async def mock_run(cmd, *args, **kwargs):
            if "test -f" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_colord_polkit()
            assert result.ok

    async def test_configure_colord_polkit_failure(self):
        from linwin.linux.tasks.xrdp import configure_colord_polkit

        async def mock_run(cmd, *args, **kwargs):
            if "test -f" in cmd:
                return _ok("no")
            return _fail()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_colord_polkit()
            assert not result.ok

    async def test_fix_ssl_permissions_already_done(self):
        from linwin.linux.tasks.xrdp import fix_xrdp_ssl_permissions
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("xrdp ssl-cert")):
            result = await fix_xrdp_ssl_permissions()
            assert result.skipped

    async def test_fix_ssl_permissions_success(self):
        from linwin.linux.tasks.xrdp import fix_xrdp_ssl_permissions

        async def mock_run(cmd, *args, **kwargs):
            if "id -nG" in cmd:
                return _ok("xrdp")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await fix_xrdp_ssl_permissions()
            assert result.ok

    async def test_fix_ssl_permissions_failure(self):
        from linwin.linux.tasks.xrdp import fix_xrdp_ssl_permissions

        async def mock_run(cmd, *args, **kwargs):
            if "id -nG" in cmd:
                return _ok("xrdp")
            return _fail()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await fix_xrdp_ssl_permissions()
            assert not result.ok

    async def test_create_systemd_overrides_already_done(self):
        from linwin.linux.tasks.xrdp import create_systemd_overrides
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("yes")):
            result = await create_systemd_overrides()
            assert result.skipped

    async def test_create_systemd_overrides_success(self):
        from linwin.linux.tasks.xrdp import create_systemd_overrides

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await create_systemd_overrides()
            assert result.ok

    async def test_create_systemd_overrides_failure(self):
        from linwin.linux.tasks.xrdp import create_systemd_overrides

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("no")
            if "tee" in cmd:
                return _fail()
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await create_systemd_overrides()
            assert not result.ok

    async def test_configure_logind_delay_already_set(self):
        from linwin.linux.tasks.xrdp import configure_logind_delay
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("yes")):
            result = await configure_logind_delay()
            assert result.skipped

    async def test_configure_logind_delay_success(self):
        from linwin.linux.tasks.xrdp import configure_logind_delay

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("no")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_logind_delay()
            assert result.ok

    async def test_configure_logind_delay_failure(self):
        from linwin.linux.tasks.xrdp import configure_logind_delay

        async def mock_run(cmd, *args, **kwargs):
            if "grep" in cmd:
                return _ok("no")
            return _fail()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await configure_logind_delay()
            assert not result.ok

    async def test_enable_user_linger_already_set(self):
        from linwin.linux.tasks.xrdp import enable_user_linger

        async def mock_run(cmd, *args, **kwargs):
            if "whoami" in cmd:
                return _ok("testuser")
            return _ok("Linger=yes")

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await enable_user_linger()
            assert result.skipped

    async def test_enable_user_linger_success(self):
        from linwin.linux.tasks.xrdp import enable_user_linger

        async def mock_run(cmd, *args, **kwargs):
            if "whoami" in cmd:
                return _ok("testuser")
            if "show-user" in cmd:
                return _ok("Linger=no")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await enable_user_linger()
            assert result.ok

    async def test_enable_user_linger_failure(self):
        from linwin.linux.tasks.xrdp import enable_user_linger

        async def mock_run(cmd, *args, **kwargs):
            if "whoami" in cmd:
                return _ok("testuser")
            if "show-user" in cmd:
                return _ok("Linger=no")
            return _fail()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await enable_user_linger()
            assert not result.ok

    async def test_mask_gdm_already_masked(self):
        from linwin.linux.tasks.xrdp import mask_gdm
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("masked")):
            result = await mask_gdm()
            assert result.skipped

    async def test_mask_gdm_not_installed(self):
        from linwin.linux.tasks.xrdp import mask_gdm
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("not-found")):
            result = await mask_gdm()
            assert result.skipped

    async def test_mask_gdm_success(self):
        from linwin.linux.tasks.xrdp import mask_gdm

        async def mock_run(cmd, *args, **kwargs):
            if "is-enabled" in cmd:
                return _ok("enabled")
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await mask_gdm()
            assert result.ok

    async def test_mask_gdm_failure(self):
        from linwin.linux.tasks.xrdp import mask_gdm

        async def mock_run(cmd, *args, **kwargs):
            if "is-enabled" in cmd:
                return _ok("enabled")
            if "mask" in cmd:
                return _fail()
            return _ok()

        with patch("linwin.linux.tasks.xrdp.run_local", side_effect=mock_run):
            result = await mask_gdm()
            assert not result.ok

    async def test_enable_xrdp_service_success(self):
        from linwin.linux.tasks.xrdp import enable_xrdp_service
        with patch("linwin.linux.tasks.xrdp.fix_xrdp_ssl_permissions", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.create_systemd_overrides", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.configure_colord_polkit", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.configure_logind_delay", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.enable_user_linger", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.mask_gdm", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok()):
            result = await enable_xrdp_service()
            assert result.ok

    async def test_enable_xrdp_service_failure(self):
        from linwin.linux.tasks.xrdp import enable_xrdp_service
        with patch("linwin.linux.tasks.xrdp.fix_xrdp_ssl_permissions", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.create_systemd_overrides", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.configure_colord_polkit", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.configure_logind_delay", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.enable_user_linger", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.mask_gdm", new_callable=AsyncMock), \
             patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_fail()):
            result = await enable_xrdp_service()
            assert not result.ok

    async def test_enable_xrdp_service_prerequisite_failure_propagates(self):
        from linwin.shared.task_result import TaskResult
        from linwin.linux.tasks.xrdp import enable_xrdp_service
        ok = TaskResult(ok=True, message="ok")
        with patch("linwin.linux.tasks.xrdp.fix_xrdp_ssl_permissions", new_callable=AsyncMock, return_value=ok), \
             patch("linwin.linux.tasks.xrdp.create_systemd_overrides", new_callable=AsyncMock, return_value=ok), \
             patch("linwin.linux.tasks.xrdp.configure_colord_polkit", new_callable=AsyncMock,
                   return_value=TaskResult(ok=False, message="tee failed")), \
             patch("linwin.linux.tasks.xrdp.configure_logind_delay", new_callable=AsyncMock, return_value=ok), \
             patch("linwin.linux.tasks.xrdp.enable_user_linger", new_callable=AsyncMock, return_value=ok), \
             patch("linwin.linux.tasks.xrdp.mask_gdm", new_callable=AsyncMock, return_value=ok), \
             patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok()):
            result = await enable_xrdp_service()
            assert not result.ok
            assert "colord polkit rule" in result.message

    async def test_check_xrdp_running_true(self):
        from linwin.linux.tasks.xrdp import check_xrdp_running
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("active")):
            assert await check_xrdp_running() is True

    async def test_check_xrdp_running_false(self):
        from linwin.linux.tasks.xrdp import check_xrdp_running
        with patch("linwin.linux.tasks.xrdp.run_local", new_callable=AsyncMock, return_value=_ok("inactive")):
            assert await check_xrdp_running() is False
