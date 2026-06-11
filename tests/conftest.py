"""Shared fixtures for RDP test modules.

The live RDP tests run against a dedicated clone of the configured
distro (default name ``linwin-test``) so they never disturb the real
one. The clone is created on first use via ``wsl --export`` /
``wsl --import`` (a few minutes, one time) and reused afterwards.

All WSL2 distros share a single network namespace, so the clone's xrdp
stack is shifted to test ports (xrdp 3391, sesman 3351) to avoid
colliding with the real distro's services.

Environment overrides:
    LINWIN_TEST_DISTRO       distro name to test against (set it to the
                             real distro's name to opt out of cloning)
    LINWIN_TEST_XRDP_PORT    xrdp port in the clone (default 3391)
    LINWIN_TEST_SESMAN_PORT  sesman port in the clone (default 3351)

To rebuild the clone from scratch: ``wsl --unregister linwin-test``.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from linwin.shared.config import load_config
from linwin.shared.subprocess_runner import run_wsl

from .helpers import _run

TEST_DISTRO = os.environ.get("LINWIN_TEST_DISTRO", "linwin-test")
TEST_XRDP_PORT = int(os.environ.get("LINWIN_TEST_XRDP_PORT", "3391"))
TEST_SESMAN_PORT = int(os.environ.get("LINWIN_TEST_SESMAN_PORT", "3351"))


def _wsl_exe(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["wsl.exe", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env={**os.environ, "WSL_UTF8": "1"},
    )


def _registered_distros() -> list[str]:
    result = _wsl_exe("-l", "-q")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _bash(distro: str, cmd: str, timeout: float = 120) -> subprocess.CompletedProcess:
    return _wsl_exe("-d", distro, "--", "bash", "-c", cmd, timeout=timeout)


def _create_test_distro(source: str, cfg) -> None:
    """Clone *source* into TEST_DISTRO and shift its xrdp stack to test ports."""
    tar_path = Path(tempfile.gettempdir()) / "linwin_test_clone.tar"
    install_dir = f"{cfg.wslDriveLetter}:\\WSL\\{TEST_DISTRO}"
    try:
        result = _wsl_exe("--export", source, str(tar_path), timeout=1800)
        if result.returncode != 0:
            pytest.skip(
                f"Could not export {source} to create the test clone: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        os.makedirs(install_dir, exist_ok=True)
        result = _wsl_exe(
            "--import", TEST_DISTRO, install_dir, str(tar_path), "--version", "2",
            timeout=1800,
        )
        if result.returncode != 0:
            pytest.skip(
                f"Could not import the test clone: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
    finally:
        tar_path.unlink(missing_ok=True)

    # Shift the clone's xrdp stack off the real distro's ports — all
    # WSL2 distros share one network namespace, so two xrdp/sesman
    # instances on the same ports would collide. xrdp discovers
    # sesman's port from sesman.ini, so the two seds stay consistent.
    fixup = (
        f"sudo sed -i '0,/^port=.*/s//port={TEST_XRDP_PORT}/' /etc/xrdp/xrdp.ini && "
        f"sudo sed -i 's/^ListenPort=.*/ListenPort={TEST_SESMAN_PORT}/' /etc/xrdp/sesman.ini && "
        f"sudo systemctl restart xrdp-sesman xrdp"
    )
    result = _bash(TEST_DISTRO, fixup, timeout=300)
    if result.returncode != 0:
        _wsl_exe("--unregister", TEST_DISTRO)
        pytest.skip(
            f"Could not configure the test clone's xrdp ports: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def test_distro():
    """The dedicated test distro, cloned from the configured one on first use."""
    cfg = load_config()
    if TEST_DISTRO == cfg.distroImportName:
        # Explicit opt-in to testing against the real distro.
        return TEST_DISTRO
    registered = _registered_distros()
    if TEST_DISTRO not in registered:
        if cfg.distroImportName not in registered:
            pytest.skip(
                f"Neither {TEST_DISTRO} nor source distro "
                f"{cfg.distroImportName} is registered"
            )
        _create_test_distro(cfg.distroImportName, cfg)
    return TEST_DISTRO


@pytest.fixture(scope="module")
def config():
    return load_config()


@pytest.fixture(scope="module")
def distro(test_distro):
    return test_distro


@pytest.fixture(scope="module")
def xrdp_port(config, distro):
    if distro == config.distroImportName:
        return config.xrdpPort
    return TEST_XRDP_PORT


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
