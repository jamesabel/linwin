"""Tests for TUI screens using Textual's run_test pilot."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from linwin.shared.config import SetupConfig
from linwin.shared.subprocess_runner import SubprocessResult


def _ok(output: str = "") -> SubprocessResult:
    return SubprocessResult(exit_code=0, stdout_lines=output.splitlines())


# ── Shared Widgets ───────────────────────────────────────────────────


def _make_app_with_screen(screen_cls):
    """Create a test app that auto-mounts the given screen class."""
    from linwin.shared.base_app import BaseSetupApp
    config = SetupConfig()

    class TestApp(BaseSetupApp):
        def on_mount(self):
            self.push_screen(screen_cls())

    return TestApp(config)


@pytest.mark.asyncio
class TestWidgets:
    async def test_task_list_widget(self):
        from linwin.shared.widgets import TaskListWidget
        from textual.screen import Screen

        class S(Screen):
            def compose(self):
                yield TaskListWidget([("t1", "Task One"), ("t2", "Task Two")], id="tasks")

        app = _make_app_with_screen(S)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            tasks = app.screen.query_one("#tasks", TaskListWidget)
            tasks.set_status("t1", "running")
            tasks.set_status("t1", "done")
            tasks.set_status("t2", "failed")
            tasks.set_status("nonexistent", "done")  # Should not crash
            tasks.set_all_pending()

    async def test_log_panel(self):
        from linwin.shared.widgets import LogPanel
        from textual.screen import Screen

        class S(Screen):
            def compose(self):
                yield LogPanel(id="log")

        app = _make_app_with_screen(S)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            log = app.screen.query_one("#log", LogPanel)
            log.write_command("echo hello")
            log.write_stdout("hello")
            log.write_stderr("warning")
            log.write_info("info msg")
            log.write_success("done")
            log.write_error("failed")
            text = log.get_text()
            assert "echo hello" in text
            assert "hello" in text
            await log.as_line_callback("output", "stdout")
            await log.as_line_callback("err", "stderr")
            log.clear()
            assert log.get_text() == ""

    async def test_verify_dashboard(self):
        from linwin.shared.widgets import VerifyDashboard
        from textual.screen import Screen

        class S(Screen):
            def compose(self):
                yield VerifyDashboard(title="Test", id="dash")

        app = _make_app_with_screen(S)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            dash = app.screen.query_one("#dash", VerifyDashboard)
            dash.add_check("check1", True)
            dash.add_check("check2", False)
            dash.add_check("check3", True, warn=True)
            assert not dash.all_passed

    async def test_verify_dashboard_all_passed(self):
        from linwin.shared.widgets import VerifyDashboard
        from textual.screen import Screen

        class S(Screen):
            def compose(self):
                yield VerifyDashboard(title="Test", id="dash")

        app = _make_app_with_screen(S)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            dash = app.screen.query_one("#dash", VerifyDashboard)
            dash.add_check("check1", True)
            dash.add_check("check2", True)
            assert dash.all_passed

    async def test_ascii_checkbox(self):
        from linwin.shared.widgets import AsciiCheckbox
        from textual.screen import Screen

        class S(Screen):
            def compose(self):
                yield AsciiCheckbox("Test CB", value=False, id="cb")

        app = _make_app_with_screen(S)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            cb = app.screen.query_one("#cb", AsciiCheckbox)
            assert cb.value is False
            cb.value = True
            assert cb.value is True

    async def test_ascii_radio_set(self):
        from linwin.shared.widgets import AsciiRadioSet
        from textual.screen import Screen

        class S(Screen):
            def compose(self):
                yield AsciiRadioSet(["A", "B", "C"], default=0, id="radio")

        app = _make_app_with_screen(S)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            radio = app.screen.query_one("#radio", AsciiRadioSet)
            assert radio.pressed_index == 0
            radio.pressed_index = 2
            assert radio.pressed_index == 2

    def test_info_row(self):
        from linwin.shared.widgets import info_row
        row = info_row("Key:", "Val")
        assert row is not None


# ── Windows Launcher Screen ──────────────────────────────────────────


@pytest.mark.asyncio
class TestLauncherScreen:
    async def test_compose_and_actions(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.launcher import LauncherScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = LauncherScreen(config)
            app.push_screen(screen)
            await pilot.pause()
            # Verify screen composed
            assert app.screen is screen

    async def test_click_dispatch(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.launcher import LauncherScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = LauncherScreen(config)
            app.push_screen(screen)
            await pilot.pause()
            # Test that CLICK_MAP is populated
            assert "btn-launch-files" in screen.CLICK_MAP
            assert "btn-exit" in screen.CLICK_MAP


# ── Windows Verify Screen ────────────────────────────────────────────


@pytest.mark.asyncio
class TestVerifyScreen:
    async def test_compose_and_verify(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.verify import VerifyScreen
        from linwin.windows.tasks.full_verify import VerifyResult, VerifyCheckItem

        config = SetupConfig()
        app = BaseSetupApp(config)

        mock_result = VerifyResult(checks=[
            VerifyCheckItem("WSL", True, category="windows"),
            VerifyCheckItem("systemd", True, category="linux"),
        ])

        with patch("linwin.windows.tasks.full_verify.run_full_verification",
                   new_callable=AsyncMock, return_value=mock_result):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = VerifyScreen(config)
                app.push_screen(screen)
                await pilot.pause()


# ── Windows Config Editor ────────────────────────────────────────────


@pytest.mark.asyncio
class TestWindowsConfigEditor:
    async def test_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.config_editor import ConfigEditorScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = ConfigEditorScreen(config)
            app.push_screen(screen)
            await pilot.pause()
            assert app.screen is screen

    async def test_save_config(self, tmp_path):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.config_editor import ConfigEditorScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = ConfigEditorScreen(config)
            app.push_screen(screen)
            await pilot.pause()
            with patch("linwin.windows.screens.config_editor.save_config"):
                screen._save_config()


# ── Linux Config Editor ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestLinuxConfigEditor:
    async def test_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.config_editor import ConfigEditorScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = ConfigEditorScreen(config)
            app.push_screen(screen)
            await pilot.pause()
            assert app.screen is screen

    async def test_save_config(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.config_editor import ConfigEditorScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = ConfigEditorScreen(config)
            app.push_screen(screen)
            await pilot.pause()
            with patch("linwin.linux.screens.config_editor.save_config"):
                screen._save_config()


# ── Linux Welcome Screen ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestWelcomeScreen:
    async def test_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.welcome import WelcomeScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        with patch("linwin.linux.screens.welcome.run_local", new_callable=AsyncMock, return_value=_ok("Ubuntu 22.04")):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = WelcomeScreen(config)
                app.push_screen(screen)
                await pilot.pause()


# ── Linux Verify Screen ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestLinuxVerifyScreen:
    async def test_compose_and_run(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.linux.screens.verify import VerifyScreen

        config = SetupConfig()
        app = BaseSetupApp(config)

        with patch("linwin.linux.screens.verify.check_systemd", new_callable=AsyncMock, return_value=(True, "systemd")), \
             patch("linwin.linux.screens.verify.check_snapd", new_callable=AsyncMock, return_value=True), \
             patch("linwin.linux.screens.verify.check_apt_package", new_callable=AsyncMock, return_value=True), \
             patch("linwin.linux.screens.verify.check_display_set", new_callable=AsyncMock, return_value=(True, ":0")), \
             patch("linwin.linux.screens.verify.check_wslg_dir", new_callable=AsyncMock, return_value=True), \
             patch("linwin.linux.screens.verify.check_drive_mounted", new_callable=AsyncMock, return_value=True):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = VerifyScreen(config)
                app.push_screen(screen)
                await pilot.pause()


# ── Windows Status Screen ────────────────────────────────────────────


@pytest.mark.asyncio
class TestStatusScreen:
    async def test_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.status import StatusScreen
        from linwin.windows.tasks.health_check import HealthStatus

        config = SetupConfig()
        health = HealthStatus(wsl_feature=True, vm_platform=True,
                              distro_registered=True, vhd_on_target=True)
        app = BaseSetupApp(config)

        with patch("linwin.windows.screens.status.validators.check_windows_build", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, message="22631", detail="OK")), \
             patch("linwin.windows.screens.status.validators.check_virtualization", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, message="Enabled", detail="")), \
             patch("linwin.windows.screens.status.validators.check_ram", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, message="64 GB", detail="")), \
             patch("linwin.windows.screens.status.validators.check_cpu_count", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, message="16 CPUs", detail="")), \
             patch("linwin.windows.screens.status.validators.check_drive_exists", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, message="Drive V:", detail="OK")):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = StatusScreen(config, health)
                app.push_screen(screen)
                await pilot.pause()

    async def test_compose_not_ready(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.status import StatusScreen
        from linwin.windows.tasks.health_check import HealthStatus

        config = SetupConfig()
        health = HealthStatus(wsl_feature=False, vm_platform=False,
                              distro_registered=False, vhd_on_target=False)
        app = BaseSetupApp(config)

        with patch("linwin.windows.screens.status.validators.check_windows_build", new_callable=AsyncMock,
                   return_value=MagicMock(ok=False, message="18362", detail="Too old")), \
             patch("linwin.windows.screens.status.validators.check_virtualization", new_callable=AsyncMock,
                   return_value=MagicMock(ok=False, message="Disabled", detail="Enable in BIOS")), \
             patch("linwin.windows.screens.status.validators.check_ram", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, message="8 GB", detail="")), \
             patch("linwin.windows.screens.status.validators.check_cpu_count", new_callable=AsyncMock,
                   return_value=MagicMock(ok=True, message="4 CPUs", detail="")), \
             patch("linwin.windows.screens.status.validators.check_drive_exists", new_callable=AsyncMock,
                   return_value=MagicMock(ok=False, message="Not found", detail="")):
            async with app.run_test(size=(80, 24)) as pilot:
                screen = StatusScreen(config, health)
                app.push_screen(screen)
                await pilot.pause()


# ── ClickDispatchScreen ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestClickDispatchScreen:
    async def test_dispatch_calls_action(self):
        from linwin.shared.base_app import BaseSetupApp, ClickDispatchScreen

        class TestScreen(ClickDispatchScreen):
            CLICK_MAP = {"btn-test": "do_thing"}
            called = False
            def compose(self):
                from textual.widgets import Static
                yield Static("test", id="btn-test")
            def action_do_thing(self):
                self.called = True

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = TestScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.click("#btn-test")
            assert screen.called

    async def test_dispatch_ignores_unmapped(self):
        from linwin.shared.base_app import BaseSetupApp, ClickDispatchScreen

        class TestScreen(ClickDispatchScreen):
            CLICK_MAP = {}
            def compose(self):
                from textual.widgets import Static
                yield Static("test", id="btn-unknown")

        config = SetupConfig()
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = TestScreen()
            app.push_screen(screen)
            await pilot.pause()
            await pilot.click("#btn-unknown")  # Should not crash


# ── Setup Proposal Screen ────────────────────────────────────────────


@pytest.mark.asyncio
class TestSetupProposalScreen:
    async def test_compose(self):
        from linwin.shared.base_app import BaseSetupApp
        from linwin.windows.screens.setup_proposal import SetupProposalScreen
        from linwin.windows.tasks.auto_config import SystemProfile
        from linwin.windows.tasks.drive_scan import DriveCandidate
        from linwin.windows.tasks.full_verify import VerifyResult, VerifyCheckItem

        config = SetupConfig()
        profile = SystemProfile(
            ram_gb=32, cpu_count=16,
            best_drive=DriveCandidate("D", 400, 1000, "SSD", "NVMe", ""),
            all_drives=[],
        )
        verify = VerifyResult(checks=[VerifyCheckItem("WSL", False)])
        app = BaseSetupApp(config)

        async with app.run_test(size=(80, 24)) as pilot:
            screen = SetupProposalScreen(config, profile, verify)
            app.push_screen(screen)
            await pilot.pause()


# ── Linux App ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestLinuxApp:
    async def test_app_mounts_welcome_screen(self):
        from linwin.linux.app import LinuxSetupApp

        config = SetupConfig()
        app = LinuxSetupApp(config)

        with patch("linwin.linux.screens.welcome.run_local", new_callable=AsyncMock, return_value=_ok("Ubuntu")):
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                from linwin.linux.screens.welcome import WelcomeScreen
                assert isinstance(app.screen, WelcomeScreen)
