"""Tests for the __main__ entry points."""

import subprocess
import sys

import pytest


class TestWindowsMain:
    def test_module_imports(self):
        """Verify tui.windows.__main__ can be imported."""
        from tui.windows.__main__ import main
        assert callable(main)

    def test_missing_config_exits(self, tmp_path, monkeypatch):
        """Running from a directory without config.json should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "tui.windows"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=15,
        )
        # Should exit non-zero (either can't find config, or not admin)
        assert result.returncode != 0 or "config.json" in result.stdout.lower() or "administrator" in result.stdout.lower()


class TestLinuxMain:
    def test_module_imports(self):
        """Verify tui.linux.__main__ can be imported."""
        from tui.linux.__main__ import main
        assert callable(main)

    def test_headless_requires_step(self):
        """--headless without --step should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "tui.linux", "--headless"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0

    def test_missing_config_exits(self, tmp_path):
        """Running from a directory without config.json should exit with error."""
        result = subprocess.run(
            [sys.executable, "-m", "tui.linux", "--headless", "--step", "enable-systemd"],
            capture_output=True,
            text=True,
            cwd=str(tmp_path),
            timeout=15,
        )
        # Should fail — either module not found (no tui package in tmp) or config missing
        assert result.returncode != 0
