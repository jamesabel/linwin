"""Shared fixtures for RDP test modules."""

from __future__ import annotations

from pathlib import Path

import pytest

from linwin.shared.config import load_config
from linwin.shared.subprocess_runner import run_wsl

from .helpers import _run

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def config():
    return load_config(CONFIG_PATH)


@pytest.fixture(scope="module")
def distro(config):
    return config.distroImportName


@pytest.fixture(scope="module")
def xrdp_port(config):
    return config.xrdpPort


@pytest.fixture(scope="module")
def xfreerdp_bin(distro):
    """Return the xfreerdp binary name, installing if needed."""
    for binary in ("xfreerdp3", "xfreerdp"):
        r = _run(run_wsl(distro, f"which {binary} 2>/dev/null"))
        if r.success and r.output.strip():
            return binary
    r = _run(run_wsl(distro, "sudo apt-get install -y freerdp2-x11 2>&1"))
    if r.success:
        return "xfreerdp"
    pytest.skip("xfreerdp not available and could not be installed")


@pytest.fixture(scope="module")
def ensure_xvfb(distro):
    """Ensure Xvfb is installed for headless display."""
    r = _run(run_wsl(distro, "which Xvfb 2>/dev/null"))
    if r.success and r.output.strip():
        return True
    r = _run(run_wsl(distro, "sudo apt-get install -y xvfb 2>&1"))
    if r.success:
        return True
    pytest.skip("Xvfb not available and could not be installed")
