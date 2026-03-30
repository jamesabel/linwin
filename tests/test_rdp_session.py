"""End-to-end RDP session test: connect, login, verify session stability.

Goes beyond auth-only testing — starts a real XFCE desktop session and
verifies it stays alive long enough for a user to interact with it.
Collects full diagnostics (sesman log, startwm log, user journal,
xfreerdp output) on failure to pinpoint exactly where the session dies.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from linwin.shared.config import load_config
from linwin.shared.subprocess_runner import run_command, run_wsl

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

TEST_USER = "_rdptest"
TEST_PASS = "WslRdpTest2024x"

# The session must stay alive at least this many seconds.
SESSION_STABILITY_SECS = 15


def _run(coro):
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
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
def rdp_test_user(distro):
    """Create a temporary Linux user for RDP auth, remove after module."""
    # Force-kill any stale sessions from previous runs
    _run(run_wsl(distro, f"sudo pkill -9 -u {TEST_USER} 2>/dev/null; sleep 2"))
    _run(run_wsl(distro, f"sudo userdel -r {TEST_USER} 2>/dev/null"))
    # Restart xrdp to clear stale session tracking
    _run(run_wsl(distro, "sudo systemctl restart xrdp xrdp-sesman"))
    _run(run_wsl(distro, "sleep 2"))

    r = _run(run_wsl(distro, f"sudo useradd -m -s /bin/bash {TEST_USER}"))
    if not r.success:
        pytest.skip(f"Could not create test user: {r.output}")
    r = _run(run_wsl(distro, f"echo '{TEST_USER}:{TEST_PASS}' | sudo chpasswd"))
    if not r.success:
        pytest.skip(f"Could not set test user password: {r.output}")
    yield TEST_USER
    # Tear down: force-kill session processes, restart xrdp, delete user
    _run(run_wsl(distro, f"sudo pkill -9 -u {TEST_USER} 2>/dev/null; sleep 2"))
    _run(run_wsl(distro, "sudo systemctl restart xrdp xrdp-sesman"))
    _run(run_wsl(distro, f"sudo userdel -r {TEST_USER} 2>/dev/null"))


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cert_flag(binary: str) -> str:
    return "/cert:ignore" if binary == "xfreerdp3" else "/cert-ignore"


def _collect_diagnostics(distro: str) -> str:
    """Collect all relevant logs after a session failure."""
    sections: list[str] = []

    checks = [
        ("xrdp-sesman.log", "sudo tail -40 /var/log/xrdp-sesman.log 2>/dev/null"),
        ("xrdp.log", "sudo tail -20 /var/log/xrdp.log 2>/dev/null"),
        ("startwm.sh", "cat /etc/xrdp/startwm.sh 2>/dev/null"),
        ("user journal", "journalctl _UID=$(id -u _rdptest 2>/dev/null) --no-pager -n 30 2>/dev/null"),
        ("system journal (xrdp)", "journalctl -u xrdp -u xrdp-sesman --no-pager -n 30 2>/dev/null"),
        ("xfce processes", "ps -u _rdptest -o pid,stat,args 2>/dev/null"),
        ("loginctl sessions", "loginctl list-sessions --no-pager 2>/dev/null"),
        ("systemd user status", "systemctl --user status 2>/dev/null"),
    ]
    for label, cmd in checks:
        r = _run(run_wsl(distro, cmd))
        text = r.output.strip() if r.success else f"(command failed: exit {r.exit_code})"
        if text:
            sections.append(f"--- {label} ---\n{text}")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRdpSessionLifecycle:
    """Start a full RDP session and verify it stays alive."""

    def test_session_survives(
        self, distro, xrdp_port, rdp_test_user, xfreerdp_bin, ensure_xvfb,
    ):
        """The server-side xfce4-session must stay alive for SESSION_STABILITY_SECS.

        Starts xfreerdp on a virtual Xvfb display to trigger session creation,
        then monitors the server-side xfce4-session process (not the xfreerdp
        client, which may crash independently of session health).
        """
        cert = _cert_flag(xfreerdp_bin)
        total_wait = SESSION_STABILITY_SECS + 30

        # Write the test script to a temp file in WSL to avoid bash -c
        # argument passing issues with wsl.exe (which breaks $!, &>, and
        # other shell features when scripts are passed inline).
        script_lines = [
            "#!/bin/bash",
            "exec 2>&1",
            "",
            f'XFREE_CMD="xvfb-run -a {xfreerdp_bin} /v:localhost:{xrdp_port}'
            f' /u:{TEST_USER} /p:{TEST_PASS} {cert}'
            f' /log-level:WARN /w:800 /h:600 /gdi:sw"',
            "",
            "cleanup() {",
            '    pkill -f xfreerdp 2>/dev/null',
            '    pkill Xvfb 2>/dev/null',
            "}",
            "trap cleanup EXIT",
            "",
            "# Start xfreerdp in background via xvfb-run",
            "$XFREE_CMD >/dev/null 2>&1 &",
            "",
            "# Wait for xfce4-session to appear (poll up to 20 seconds)",
            "SESSION_FOUND=0",
            "for WAIT in $(seq 1 20); do",
            "    sleep 1",
            f'    if pgrep -u {TEST_USER} xfce4-session >/dev/null 2>&1; then',
            "        SESSION_FOUND=1",
            '        echo "xfce4-session appeared after ${WAIT}s"',
            "        break",
            "    fi",
            "done",
            "",
            'if [ "$SESSION_FOUND" -eq 0 ]; then',
            '    echo "XFCE_SESSION_NOT_STARTED (waited 20s)"',
            '    echo "=== sesman log ==="',
            "    sudo tail -20 /var/log/xrdp-sesman.log 2>/dev/null",
            f'    echo "=== processes for {TEST_USER} ==="',
            f"    ps -u {TEST_USER} -o pid,etimes,stat,args 2>/dev/null"
            ' || echo "(no processes)"',
            "    exit 1",
            "fi",
            "",
            "# Poll the server-side xfce4-session",
            "ALIVE_SECS=0",
            f"for i in $(seq 1 {SESSION_STABILITY_SECS}); do",
            "    sleep 1",
            f"    if ! pgrep -u {TEST_USER} xfce4-session >/dev/null 2>&1; then",
            "        ALIVE_SECS=$i",
            '        echo "XFCE_SESSION_DIED_AT=${ALIVE_SECS}s"',
            "        sudo tail -30 /var/log/xrdp-sesman.log 2>/dev/null",
            f"        ps -u {TEST_USER} -o pid,etimes,stat,args 2>/dev/null",
            "        exit 1",
            "    fi",
            "    ALIVE_SECS=$i",
            "done",
            "",
            'echo "SESSION_ALIVE duration=${ALIVE_SECS}s"',
            f'pgrep -u {TEST_USER} xfce4-session >/dev/null 2>&1'
            ' && echo "XFCE_SESSION=running" || echo "XFCE_SESSION=missing"',
            f'pgrep -u {TEST_USER} xfwm4 >/dev/null 2>&1'
            ' && echo "XFWM4=running" || echo "XFWM4=missing"',
            f'pgrep -u {TEST_USER} xfce4-panel >/dev/null 2>&1'
            ' && echo "XFCE4_PANEL=running" || echo "XFCE4_PANEL=missing"',
        ]

        # Write script to Windows temp, then copy to WSL
        import tempfile, os
        script_content = "\n".join(script_lines) + "\n"
        tmp = os.path.join(tempfile.gettempdir(), "rdp_session_test.sh")
        with open(tmp, "w", newline="\n") as f:
            f.write(script_content)

        # Convert Windows path to WSL path and copy
        wsl_tmp = tmp.replace("\\", "/").replace("C:", "/mnt/c")
        _run(run_wsl(distro, f"cp '{wsl_tmp}' /tmp/rdp_session_test.sh && chmod +x /tmp/rdp_session_test.sh"))

        result = _run(run_command(
            ["wsl.exe", "-d", distro, "--", "bash", "/tmp/rdp_session_test.sh"],
            timeout=float(total_wait + 30),
        ))

        output = result.output

        if "SESSION_ALIVE" in output:
            return  # success

        # --- Failure: build a detailed report ---
        diagnostics = _collect_diagnostics(distro)

        died_at = "unknown"
        for line in output.splitlines():
            if "XFCE_SESSION_DIED_AT=" in line:
                died_at = line.split("=", 1)[1]
            elif "XFCE_SESSION_NOT_STARTED" in line:
                died_at = "never started (within 20s)"

        pytest.fail(
            f"\n{'='*60}\n"
            f"xfce4-session died after {died_at} "
            f"(needed {SESSION_STABILITY_SECS}s)\n"
            f"{'='*60}\n\n"
            f"--- script output ---\n{output}\n\n"
            f"{diagnostics}"
        )

    def test_xfce_session_process_present(
        self, distro, xrdp_port, rdp_test_user, xfreerdp_bin, ensure_xvfb,
    ):
        """After connecting, xfce4-session must be running for the test user."""
        cert = _cert_flag(xfreerdp_bin)
        total_wait = 45

        script_lines = [
            "#!/bin/bash",
            "exec 2>&1",
            "",
            "cleanup() {",
            "    pkill -f xfreerdp 2>/dev/null",
            "    pkill Xvfb 2>/dev/null",
            "}",
            "trap cleanup EXIT",
            "",
            f'xvfb-run -a {xfreerdp_bin} /v:localhost:{xrdp_port}'
            f' /u:{TEST_USER} /p:{TEST_PASS} {cert}'
            f' /log-level:ERROR /w:800 /h:600 /gdi:sw >/dev/null 2>&1 &',
            "",
            "# Wait for desktop to start (poll for xfce4-session)",
            "SESSION_FOUND=0",
            "for WAIT in $(seq 1 15); do",
            "    sleep 1",
            f"    if pgrep -u {TEST_USER} xfce4-session >/dev/null 2>&1; then",
            "        SESSION_FOUND=1",
            "        break",
            "    fi",
            "done",
            'if [ "$SESSION_FOUND" -eq 0 ]; then',
            '    echo "XFREERDP_DEAD"',
            "    exit 1",
            "fi",
            "",
            f'pgrep -u {TEST_USER} xfce4-session >/dev/null 2>&1'
            ' && echo "XFCE_SESSION=running" || echo "XFCE_SESSION=missing"',
            f'pgrep -u {TEST_USER} xfwm4 >/dev/null 2>&1'
            ' && echo "XFWM4=running" || echo "XFWM4=missing"',
            f'pgrep -u {TEST_USER} xfce4-panel >/dev/null 2>&1'
            ' && echo "XFCE4_PANEL=running" || echo "XFCE4_PANEL=missing"',
        ]

        import tempfile, os
        script_content = "\n".join(script_lines) + "\n"
        tmp = os.path.join(tempfile.gettempdir(), "rdp_process_test.sh")
        with open(tmp, "w", newline="\n") as f:
            f.write(script_content)

        wsl_tmp = tmp.replace("\\", "/").replace("C:", "/mnt/c")
        _run(run_wsl(distro, f"cp '{wsl_tmp}' /tmp/rdp_process_test.sh && chmod +x /tmp/rdp_process_test.sh"))

        result = _run(run_command(
            ["wsl.exe", "-d", distro, "--", "bash", "/tmp/rdp_process_test.sh"],
            timeout=float(total_wait + 30),
        ))

        output = result.output

        if "XFREERDP_DEAD" in output:
            diagnostics = _collect_diagnostics(distro)
            pytest.fail(
                f"xfce4-session not started within 15s.\n\n"
                f"--- output ---\n{output}\n\n"
                f"{diagnostics}"
            )

        assert "XFCE_SESSION=running" in output, (
            f"xfce4-session not running.\nOutput:\n{output}"
        )
