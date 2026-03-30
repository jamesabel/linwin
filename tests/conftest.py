"""Shared fixtures and utilities for RDP test modules."""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import pytest

from linwin.shared.config import load_config
from linwin.shared.subprocess_runner import run_wsl

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    """Receive exactly *n* bytes from *sock*, or raise on early close."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError(
                f"Connection closed after {len(buf)}/{n} bytes"
            )
        buf += chunk
    return buf


def _cert_flag(binary: str) -> str:
    """Return the correct cert-ignore flag for the freerdp version."""
    return "/cert:ignore" if binary == "xfreerdp3" else "/cert-ignore"


def _collect_diagnostics(distro: str, user: str) -> str:
    """Collect all relevant logs after a session failure."""
    sections: list[str] = []

    checks = [
        ("xrdp-sesman.log", "sudo tail -40 /var/log/xrdp-sesman.log 2>/dev/null"),
        ("xrdp.log", "sudo tail -20 /var/log/xrdp.log 2>/dev/null"),
        ("startwm log", f"cat /tmp/xrdp-startwm-{user}.log 2>/dev/null"),
        ("startwm.sh", "cat /etc/xrdp/startwm.sh 2>/dev/null"),
        ("system journal (xrdp)", "journalctl -u xrdp -u xrdp-sesman --no-pager -n 30 2>/dev/null"),
        ("user processes", f"ps -u {user} -o pid,etimes,stat,args 2>/dev/null"),
        ("loginctl sessions", "loginctl list-sessions --no-pager 2>/dev/null"),
        ("boot list (last 5)", "journalctl --list-boots 2>/dev/null | tail -5"),
    ]
    for label, cmd in checks:
        r = _run(run_wsl(distro, cmd))
        text = r.output.strip() if r.success else f"(command failed: exit {r.exit_code})"
        if text:
            sections.append(f"--- {label} ---\n{text}")

    return "\n\n".join(sections)


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
