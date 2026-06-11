"""Tests for shared/launcher.py and the top-level dispatcher."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestLaunchRdp:
    def test_uses_wsl_ip_when_available(self):
        from linwin.shared import launcher
        with patch.object(launcher, "ensure_wsl_keepalive") as keepalive, \
             patch.object(launcher, "_get_wsl_ip", return_value="172.20.1.2"), \
             patch.object(launcher.subprocess, "Popen") as popen:
            launcher.launch_rdp(port=3390, distro="Ubuntu")
        keepalive.assert_called_once()
        assert popen.call_args.args[0] == ["mstsc.exe", "/v:172.20.1.2:3390"]

    def test_falls_back_to_localhost(self):
        from linwin.shared import launcher
        with patch.object(launcher, "ensure_wsl_keepalive"), \
             patch.object(launcher, "_get_wsl_ip", return_value=""), \
             patch.object(launcher.subprocess, "Popen") as popen:
            launcher.launch_rdp(port=3391)
        # WSL2 localhostForwarding makes the loopback reachable
        assert popen.call_args.args[0] == ["mstsc.exe", "/v:127.0.0.1:3391"]


class TestGetWslIp:
    def test_parses_first_ip(self):
        from linwin.shared import launcher
        proc = MagicMock(stdout="172.20.1.2 10.0.0.5\n")
        with patch.object(launcher.subprocess, "run", return_value=proc):
            assert launcher._get_wsl_ip("Ubuntu") == "172.20.1.2"

    def test_returns_empty_on_failure(self):
        from linwin.shared import launcher
        with patch.object(launcher.subprocess, "run", side_effect=OSError("no wsl")):
            assert launcher._get_wsl_ip("Ubuntu") == ""

    def test_returns_empty_on_blank_output(self):
        from linwin.shared import launcher
        proc = MagicMock(stdout="\n")
        with patch.object(launcher.subprocess, "run", return_value=proc):
            assert launcher._get_wsl_ip("Ubuntu") == ""


class TestKeepalive:
    def test_starts_once_and_reuses(self):
        from linwin.shared import launcher
        running = MagicMock()
        running.poll.return_value = None  # still alive
        with patch.object(launcher, "_keepalive_proc", None), \
             patch.object(launcher.subprocess, "Popen", return_value=running) as popen:
            launcher.ensure_wsl_keepalive("Ubuntu")
            launcher.ensure_wsl_keepalive("Ubuntu")
        assert popen.call_count == 1
        assert "sleep" in popen.call_args.args[0]


class TestNotifyLaunch:
    def test_success_notifies(self):
        from linwin.shared import launcher
        app = MagicMock()
        with patch.object(launcher, "launch_wsl_app") as launch:
            launcher.notify_launch(app, "nautilus", "File Manager", "Ubuntu")
        launch.assert_called_once_with("Ubuntu", "nautilus")
        assert "Launched" in app.notify.call_args.args[0]

    def test_failure_notifies_error(self):
        from linwin.shared import launcher
        app = MagicMock()
        with patch.object(launcher, "launch_wsl_app", side_effect=OSError("boom")):
            launcher.notify_launch(app, "nautilus", "File Manager", "Ubuntu")
        assert app.notify.call_args.kwargs.get("severity") == "error"


class TestTopLevelDispatcher:
    def test_dispatches_to_platform_main(self):
        from linwin.__main__ import main
        with patch("linwin.windows.__main__.main") as win_main, \
             patch("linwin.linux.__main__.main") as linux_main:
            main()
        # Exactly one platform entry point ran
        assert win_main.called != linux_main.called
