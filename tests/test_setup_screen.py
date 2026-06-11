"""Tests for the Windows SetupScreen flow: happy path, reboot, resume, abort."""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linwin.shared.config import SetupConfig
from linwin.shared.subprocess_runner import SubprocessResult
from linwin.shared.task_result import TaskResult


def _tr(ok: bool = True, message: str = "", skipped: bool = False) -> TaskResult:
    return TaskResult(ok=ok, message=message, skipped=skipped)


def _setup_patches(overrides: dict | None = None) -> tuple[list, dict]:
    """Build the standard everything-succeeds patch set for run_setup.

    Returns (patchers, mocks) where mocks maps short names to the mock
    objects so tests can assert on calls.
    """
    from linwin.windows.tasks.features import FeatureResult

    mocks: dict[str, object] = {}

    def add(key, target, mock):
        mocks[key] = mock
        return patch(target, mock)

    o = overrides or {}
    patchers = [
        add("check_windows_build", "linwin.windows.tasks.validators.check_windows_build",
            AsyncMock(return_value=o.get("check_windows_build", _tr(message="build 26200")))),
        add("check_virtualization", "linwin.windows.tasks.validators.check_virtualization",
            AsyncMock(return_value=_tr(message="Virtualization enabled"))),
        add("check_drive_exists", "linwin.windows.tasks.validators.check_drive_exists",
            AsyncMock(return_value=_tr(message="Drive found"))),
        add("check_feature", "linwin.windows.tasks.features.check_feature",
            AsyncMock(return_value=o.get("feature_enabled", True))),
        add("enable_wsl_feature", "linwin.windows.tasks.features.enable_wsl_feature",
            AsyncMock(return_value=o.get("enable_result",
                                         FeatureResult(already_enabled=False, enabled_now=True)))),
        add("enable_vm_platform", "linwin.windows.tasks.features.enable_vm_platform",
            AsyncMock(return_value=o.get("enable_result",
                                         FeatureResult(already_enabled=False, enabled_now=True)))),
        add("update_wsl", "linwin.windows.tasks.wsl_install.update_wsl",
            AsyncMock(return_value=o.get("update_wsl", _tr(message="WSL updated")))),
        add("set_version", "linwin.windows.tasks.wsl_install.set_wsl_default_version",
            AsyncMock(return_value=_tr(message="Version 2"))),
        add("install_distro", "linwin.windows.tasks.wsl_install.install_distro",
            AsyncMock(return_value=_tr(message="already registered", skipped=True))),
        add("export_distro", "linwin.windows.tasks.wsl_install.export_distro",
            AsyncMock(return_value=(_tr(message="already on target", skipped=True), ""))),
        add("import_distro", "linwin.windows.tasks.wsl_install.import_distro",
            AsyncMock(return_value=_tr(message="imported"))),
        add("get_configured_default_user", "linwin.windows.tasks.wsl_install.get_configured_default_user",
            AsyncMock(return_value="ubuntu")),
        add("user_exists", "linwin.windows.tasks.wsl_install.user_exists",
            AsyncMock(return_value=True)),
        add("detect_default_user", "linwin.windows.tasks.wsl_install.detect_default_user",
            AsyncMock(return_value="ubuntu")),
        add("create_default_user", "linwin.windows.tasks.wsl_install.create_default_user",
            AsyncMock(return_value=_tr(message="created"))),
        add("ensure_passwordless_sudo", "linwin.windows.tasks.wsl_install.ensure_passwordless_sudo",
            AsyncMock(return_value=_tr(message="configured", skipped=True))),
        add("get_password_status", "linwin.windows.tasks.wsl_install.get_password_status",
            AsyncMock(return_value=o.get("password_status", "P"))),
        add("set_user_password", "linwin.windows.tasks.wsl_install.set_user_password",
            AsyncMock(return_value=_tr(message="Password set"))),
        add("set_default_user", "linwin.windows.tasks.wsl_install.set_default_user",
            AsyncMock(return_value=_tr(message="already set", skipped=True))),
        add("shutdown_wsl", "linwin.windows.tasks.wsl_install.shutdown_wsl",
            AsyncMock(return_value=_tr(message="WSL shut down"))),
        add("wait_for_wsl_ready", "linwin.windows.tasks.wsl_install.wait_for_wsl_ready",
            AsyncMock(return_value=True)),
        add("write_wslconfig", "linwin.windows.screens.setup.write_wslconfig",
            MagicMock(return_value=_tr(message="written"))),
        add("run_linux_headless", "linwin.windows.screens.setup.run_linux_headless",
            AsyncMock(return_value=o.get("linux_result", SubprocessResult(exit_code=0)))),
        add("save_state", "linwin.windows.screens.setup.save_state", MagicMock()),
        add("clear_state", "linwin.windows.screens.setup.clear_state", MagicMock()),
    ]
    return patchers, mocks


async def _run_screen(app, screen) -> None:
    async with app.run_test(size=(100, 40)) as pilot:
        app.push_screen(screen)
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()


@pytest.mark.asyncio
class TestSetupScreenFlow:
    async def test_happy_path_runs_all_tasks(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches()

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            await _run_screen(app, SetupScreen(config))

        # All three Linux steps ran, in order
        steps = [c.args[1] for c in mocks["run_linux_headless"].await_args_list]
        assert steps == ["enable-systemd", "install-packages", "configure-xrdp"]
        # Flow completed: state cleared, no reboot state saved
        mocks["clear_state"].assert_called_once()
        mocks["save_state"].assert_not_called()
        # Features were already enabled, so no DISM enables ran
        mocks["enable_wsl_feature"].assert_not_awaited()
        mocks["enable_vm_platform"].assert_not_awaited()

    async def test_reboot_checkpoint_saves_state_and_stops(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen
        from linwin.windows.tasks.setup_tasks import RESUME_AFTER_REBOOT

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches({"feature_enabled": False})

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            await _run_screen(app, SetupScreen(config))

        # Both features got enabled, reboot state saved pointing at the resume task
        mocks["enable_wsl_feature"].assert_awaited_once()
        mocks["enable_vm_platform"].assert_awaited_once()
        mocks["save_state"].assert_called_once()
        state = mocks["save_state"].call_args.args[0]
        assert state.resume_from_task == RESUME_AFTER_REBOOT
        # Flow stopped at the checkpoint: nothing after it ran
        mocks["update_wsl"].assert_not_awaited()
        mocks["run_linux_headless"].assert_not_awaited()
        mocks["clear_state"].assert_not_called()

    async def test_resume_skips_pre_reboot_tasks(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches()

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            await _run_screen(app, SetupScreen(config, resume_from="update_wsl"))

        # Pre-reboot checks were skipped entirely
        mocks["check_windows_build"].assert_not_awaited()
        mocks["check_feature"].assert_not_awaited()
        # Post-reboot flow ran to completion
        mocks["update_wsl"].assert_awaited_once()
        assert mocks["run_linux_headless"].await_count == 3
        mocks["clear_state"].assert_called_once()

    async def test_failure_aborts_flow(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches(
            {"update_wsl": _tr(ok=False, message="WSL update failed")}
        )

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            await _run_screen(app, SetupScreen(config))

        mocks["update_wsl"].assert_awaited_once()
        # Abort: nothing after the failed task ran, state not cleared
        mocks["set_version"].assert_not_awaited()
        mocks["run_linux_headless"].assert_not_awaited()
        mocks["clear_state"].assert_not_called()

    async def test_locked_password_prompts_and_sets(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches({"password_status": "L"})

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            stack.enter_context(patch.object(
                app, "push_screen_wait", AsyncMock(return_value="hunter2")))
            await _run_screen(app, SetupScreen(config))

        # Locked password -> the prompt's answer is applied to the user
        args = mocks["set_user_password"].await_args.args
        assert args[1] == "ubuntu" and args[2] == "hunter2"

    async def test_locked_password_prompt_skipped(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches({"password_status": "L"})

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            stack.enter_context(patch.object(
                app, "push_screen_wait", AsyncMock(return_value=None)))
            await _run_screen(app, SetupScreen(config))

        # User skipped the prompt -> nothing applied, flow continues
        mocks["set_user_password"].assert_not_awaited()
        mocks["clear_state"].assert_called_once()

    async def test_set_password_not_prompted_when_already_set(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches()  # password_status "P"

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            prompt = stack.enter_context(patch.object(
                app, "push_screen_wait", AsyncMock(return_value="unused")))
            await _run_screen(app, SetupScreen(config))

        prompt.assert_not_awaited()
        mocks["set_user_password"].assert_not_awaited()

    async def test_ghost_configured_user_falls_back_to_detection(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup import SetupScreen

        config = SetupConfig()
        app = BaseSetupApp(config)
        patchers, mocks = _setup_patches()
        mocks["get_configured_default_user"].return_value = "ghost"
        mocks["user_exists"].return_value = False
        mocks["set_default_user"].return_value = _tr(message="Default user set to ubuntu")

        with ExitStack() as stack:
            for p in patchers:
                stack.enter_context(p)
            await _run_screen(app, SetupScreen(config))

        # The stale configured user was rejected and detection ran
        mocks["detect_default_user"].assert_awaited_once()
        sudo_user = mocks["ensure_passwordless_sudo"].await_args.args[1]
        assert sudo_user == "ubuntu"
        set_user = mocks["set_default_user"].await_args.args[1]
        assert set_user == "ubuntu"
