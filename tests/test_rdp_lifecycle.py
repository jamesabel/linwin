"""End-to-end lifecycle test: two consecutive RDP sessions using the
production ensure_wsl_keepalive() to keep the WSL VM alive.

Validates the full user lifecycle:
  launch app -> RDP into Ubuntu -> open an app -> close session
repeated TWICE, verifying:
  - Each session starts and runs stably
  - The production keepalive prevents VM shutdown between sessions
  - xrdp remains operational throughout and after both sessions
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time

import pytest

import linwin.shared.launcher as launcher_mod
from linwin.shared.launcher import ensure_wsl_keepalive
from linwin.shared.subprocess_runner import run_command, run_wsl
from .helpers import (
    _assert_xrdp_accepts_connections,
    _cert_flag,
    _collect_diagnostics,
    _run,
)

TEMP_PASSWORD = "TempRdpLifecycleTest2024x"
SESSION_STABILITY_SECS = 15


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def production_keepalive(distro):
    """Start the WSL keepalive using the PRODUCTION ensure_wsl_keepalive().

    This validates that the actual production code in launcher.py works
    correctly to keep the WSL VM alive after the TUI process exits.
    """
    ensure_wsl_keepalive(distro)

    proc = launcher_mod._keepalive_proc
    assert proc is not None, "ensure_wsl_keepalive did not create a process"
    assert proc.poll() is None, "keepalive process exited immediately"

    # Wait for WSL to be ready
    for _ in range(10):
        r = _run(run_wsl(distro, "echo ready"))
        if r.success and "ready" in r.output:
            break
        time.sleep(1)
    else:
        pytest.fail("WSL did not become ready after ensure_wsl_keepalive()")

    yield proc

    # Teardown: kill the production keepalive and reset the module global
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    launcher_mod._keepalive_proc = None


@pytest.fixture(scope="module")
def primary_user(distro, production_keepalive):
    """Find the UID 1000 user (the primary Ubuntu user)."""
    r = _run(run_wsl(distro, "getent passwd 1000 | cut -d: -f1"))
    user = r.output.strip()
    if not r.success or not user:
        pytest.skip("No UID 1000 user found in WSL distro")
    return user


@pytest.fixture(scope="module")
def rdp_user(distro, primary_user):
    """Set temp password, clean stale sessions, restore password on teardown."""
    r = _run(run_wsl(distro, f"sudo getent shadow {primary_user} | cut -d: -f2"))
    original_hash = r.output.strip() if r.success else ""

    r = _run(run_wsl(distro, f"echo '{primary_user}:{TEMP_PASSWORD}' | sudo chpasswd"))
    if not r.success:
        pytest.skip(f"Could not set password for {primary_user}: {r.output}")

    _run(run_wsl(distro, f"sudo pkill -9 -u {primary_user} xfce4-session 2>/dev/null"))
    _run(run_wsl(distro, "sleep 1"))
    _run(run_wsl(distro, "sudo systemctl restart xrdp xrdp-sesman"))
    _run(run_wsl(distro, "sleep 2"))

    yield primary_user

    # Teardown: kill session processes, restore password
    _run(run_wsl(distro, f"sudo pkill -9 -u {primary_user} xfce4-session 2>/dev/null"))
    _run(run_wsl(distro, f"sudo pkill -f xfreerdp 2>/dev/null"))
    _run(run_wsl(distro, f"sudo pkill Xvfb 2>/dev/null"))
    _run(run_wsl(distro, "sleep 1"))
    if original_hash:
        hash_file = os.path.join(tempfile.gettempdir(), "pw_restore_lifecycle.txt")
        with open(hash_file, "w", newline="\n") as hf:
            hf.write(f"{primary_user}:{original_hash}\n")
        wsl_hash = hash_file.replace("\\", "/")
        wsl_hash = f"/mnt/{wsl_hash[0].lower()}{wsl_hash[2:]}"
        _run(run_wsl(distro, f"sudo chpasswd -e < '{wsl_hash}'"))
        os.unlink(hash_file)
    else:
        _run(run_wsl(distro, f"sudo passwd -u {primary_user}"))


@pytest.fixture(scope="module")
def xfreerdp_bin(distro, production_keepalive):
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
def ensure_tools(distro, production_keepalive):
    """Ensure xdotool and imagemagick are installed."""
    for pkg, binary in [("xdotool", "xdotool"), ("imagemagick", "import")]:
        r = _run(run_wsl(distro, f"which {binary} 2>/dev/null"))
        if r.success and r.output.strip():
            continue
        r = _run(run_wsl(distro, f"sudo apt-get install -y {pkg} 2>&1"))
        if not r.success:
            pytest.skip(f"{pkg} not available and could not be installed")
    return True


@pytest.fixture(scope="module")
def ensure_xvfb(distro, production_keepalive):
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

def _assert_wsl_vm_alive(distro: str):
    """Assert the WSL VM is still alive by running a trivial command."""
    r = _run(run_wsl(distro, "echo alive"))
    assert r.success and "alive" in r.output, (
        f"WSL VM appears to have shut down: exit={r.exit_code}, output={r.output}"
    )


def _run_lifecycle_session(
    distro: str,
    xrdp_port: int,
    user: str,
    password: str,
    xfreerdp_bin: str,
    session_label: str,
    stability_secs: int = SESSION_STABILITY_SECS,
) -> tuple[bool, str]:
    """Connect via RDP, launch xfce4-terminal, verify stability.

    Returns (success: bool, output: str).
    """
    cert = _cert_flag(xfreerdp_bin)

    script = f"""#!/bin/bash
exec 2>&1
set -o pipefail

USER="{user}"
PASS="{password}"
XFREERDP="{xfreerdp_bin}"
PORT="{xrdp_port}"
CERT="{cert}"
STABILITY_SECS={stability_secs}
LABEL="{session_label}"

sudo mkdir -p /tmp/rdp_lifecycle_screenshots
sudo chmod 777 /tmp/rdp_lifecycle_screenshots

cleanup() {{
    pkill -f xfreerdp 2>/dev/null
    pkill Xvfb 2>/dev/null
}}
trap cleanup EXIT

# --- Start xfreerdp via xvfb-run in background ---
xvfb-run -a $XFREERDP /v:localhost:$PORT /u:$USER /p:$PASS $CERT \\
    /log-level:WARN /w:1024 /h:768 /gdi:sw >/dev/null 2>&1 &

# --- Poll for xfce4-session (up to 30 seconds) ---
SESSION_FOUND=0
for WAIT in $(seq 1 30); do
    sleep 1
    if pgrep -u $USER xfce4-session >/dev/null 2>&1; then
        SESSION_FOUND=1
        echo "${{LABEL}}: xfce4-session appeared after ${{WAIT}}s"
        break
    fi
done

if [ "$SESSION_FOUND" -eq 0 ]; then
    echo "FAIL:${{LABEL}}: xfce4-session not started within 30s"
    sudo tail -20 /var/log/xrdp-sesman.log 2>/dev/null
    cat /tmp/xrdp-startwm-${{USER}}.log 2>/dev/null
    ps -u $USER -o pid,etimes,stat,args 2>/dev/null
    exit 1
fi

# --- Find the display ---
DISP=
XFCE_PID=$(pgrep -u $USER xfce4-session 2>/dev/null | head -1)
if [ -n "$XFCE_PID" ]; then
    DISP=$(cat /proc/$XFCE_PID/environ 2>/dev/null | tr "\\0" "\\n" | grep "^DISPLAY=" | cut -d= -f2)
fi

if [ -z "$DISP" ]; then
    echo "FAIL:${{LABEL}}: could not determine DISPLAY"
    exit 1
fi
echo "${{LABEL}}: display=$DISP"

sleep 3

# --- Take desktop screenshot ---
sudo -u $USER DISPLAY=$DISP XAUTHORITY=/home/$USER/.Xauthority \\
    import -window root /tmp/rdp_lifecycle_screenshots/${{LABEL}}_desktop.png 2>&1 || \\
    echo "WARNING: desktop screenshot failed"

# --- Launch xfce4-terminal ---
sudo -u $USER DISPLAY=$DISP XAUTHORITY=/home/$USER/.Xauthority \\
    xfce4-terminal &

# --- Wait for terminal window (poll xdotool for up to 10s) ---
TERM_FOUND=0
for TWAIT in $(seq 1 10); do
    sleep 1
    WINS=$(sudo -u $USER DISPLAY=$DISP XAUTHORITY=/home/$USER/.Xauthority \\
        xdotool search --name "Terminal" 2>/dev/null)
    if [ -n "$WINS" ]; then
        TERM_FOUND=1
        echo "${{LABEL}}: xfce4-terminal window found after ${{TWAIT}}s"
        break
    fi
done

if [ "$TERM_FOUND" -eq 0 ]; then
    echo "WARNING:${{LABEL}}: xfce4-terminal window not detected via xdotool (continuing)"
fi

# --- Take screenshot with terminal ---
sudo -u $USER DISPLAY=$DISP XAUTHORITY=/home/$USER/.Xauthority \\
    import -window root /tmp/rdp_lifecycle_screenshots/${{LABEL}}_with_terminal.png 2>&1 || \\
    echo "WARNING: terminal screenshot failed"

# --- Monitor session stability ---
echo "${{LABEL}}: monitoring stability for ${{STABILITY_SECS}}s..."
for i in $(seq 1 $STABILITY_SECS); do
    sleep 1
    if ! pgrep -u $USER xfce4-session >/dev/null 2>&1; then
        echo "FAIL:${{LABEL}}: xfce4-session died at ${{i}}s"
        sudo tail -20 /var/log/xrdp-sesman.log 2>/dev/null
        exit 1
    fi
done

echo "${{LABEL}}: SESSION_ALIVE duration=${{STABILITY_SECS}}s"
echo "SUCCESS"
"""

    tmp = os.path.join(tempfile.gettempdir(), f"rdp_lifecycle_{session_label}.sh")
    with open(tmp, "w", newline="\n") as f:
        f.write(script)

    wsl_tmp = tmp.replace("\\", "/")
    wsl_tmp = f"/mnt/{wsl_tmp[0].lower()}{wsl_tmp[2:]}"
    _run(run_wsl(
        distro,
        f"cp '{wsl_tmp}' /tmp/rdp_lifecycle_{session_label}.sh "
        f"&& chmod +x /tmp/rdp_lifecycle_{session_label}.sh",
    ))

    total_timeout = stability_secs + 90
    result = _run(run_command(
        ["wsl.exe", "-d", distro, "--", "bash",
         f"/tmp/rdp_lifecycle_{session_label}.sh"],
        timeout=float(total_timeout),
    ))

    return ("SUCCESS" in result.output, result.output)


# ---------------------------------------------------------------------------
# Screenshot directory
# ---------------------------------------------------------------------------

_screenshot_local_dir = os.path.join(tempfile.gettempdir(), "rdp_lifecycle_screenshots")
os.makedirs(_screenshot_local_dir, exist_ok=True)


def _copy_screenshot(distro: str, wsl_path: str) -> None:
    """Copy a screenshot from WSL to the local Windows temp directory."""
    basename = os.path.basename(wsl_path)
    local_path = os.path.join(_screenshot_local_dir, basename)
    wsl_local = local_path.replace("\\", "/")
    wsl_local = f"/mnt/{wsl_local[0].lower()}{wsl_local[2:]}"
    _run(run_wsl(distro, f"test -f '{wsl_path}' && cp '{wsl_path}' '{wsl_local}' 2>/dev/null"))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRdpLifecycle:
    """End-to-end test: two consecutive RDP sessions with app launch,
    using the production ensure_wsl_keepalive() to keep the VM alive."""

    def test_production_keepalive_starts(self, production_keepalive):
        """Verify ensure_wsl_keepalive() created a running process."""
        assert production_keepalive.poll() is None, (
            "Production keepalive process is not running"
        )

    def test_two_sessions_with_keepalive(
        self,
        distro,
        xrdp_port,
        rdp_user,
        xfreerdp_bin,
        ensure_xvfb,
        ensure_tools,
        production_keepalive,
    ):
        """Run the full lifecycle TWICE:
        connect -> verify desktop -> launch terminal -> verify stability -> disconnect.

        Between sessions: kill client-side processes, verify VM is still alive
        via the production keepalive. Both sessions must succeed.
        """
        user = rdp_user
        failures = []

        for attempt, label in enumerate(["lifecycle_s1", "lifecycle_s2"], 1):
            # -- Pre-session: verify xrdp accepts connections --
            try:
                _assert_xrdp_accepts_connections(distro, xrdp_port)
            except Exception:
                time.sleep(3)
                try:
                    _assert_xrdp_accepts_connections(distro, xrdp_port)
                except Exception as e2:
                    failures.append(
                        f"Session {attempt} ({label}): xrdp not accepting "
                        f"connections before session start: {e2}"
                    )
                    break

            # -- Clean up stale session from previous attempt --
            if attempt > 1:
                _run(run_wsl(distro, f"sudo pkill -9 -u {user} xfce4-session 2>/dev/null"))
                _run(run_wsl(distro, "sleep 3"))

            # -- Run the session (always launch app) --
            success, output = _run_lifecycle_session(
                distro, xrdp_port, user, TEMP_PASSWORD,
                xfreerdp_bin, label,
            )

            # -- Copy screenshots to Windows --
            for suffix in ("desktop", "with_terminal"):
                _copy_screenshot(
                    distro,
                    f"/tmp/rdp_lifecycle_screenshots/{label}_{suffix}.png",
                )

            if not success:
                diagnostics = _collect_diagnostics(distro, user)
                failures.append(
                    f"\n{'='*60}\n"
                    f"Session {attempt} ({label}) FAILED\n"
                    f"{'='*60}\n\n"
                    f"--- script output ---\n{output}\n\n"
                    f"--- screenshots in ---\n{_screenshot_local_dir}\n\n"
                    f"{diagnostics}"
                )
                break

            # -- Post-session: disconnect and clean up client side --
            _run(run_wsl(distro, f"sudo pkill -9 -u {user} xfce4-session 2>/dev/null"))
            _run(run_wsl(distro, f"sudo pkill -f xfreerdp 2>/dev/null"))
            _run(run_wsl(distro, f"sudo pkill Xvfb 2>/dev/null"))
            _run(run_wsl(distro, "sleep 3"))

            # -- CRITICAL: verify VM survived session disconnect --
            _assert_wsl_vm_alive(distro)

            # Verify the production keepalive process is still running
            assert production_keepalive.poll() is None, (
                f"Production keepalive process died after session {attempt}"
            )

        if failures:
            pytest.fail("\n".join(failures))

    def test_keepalive_idempotent(self, distro, production_keepalive):
        """Calling ensure_wsl_keepalive() again must not spawn a second process."""
        original_pid = production_keepalive.pid
        ensure_wsl_keepalive(distro)
        current_proc = launcher_mod._keepalive_proc
        assert current_proc.pid == original_pid, (
            f"ensure_wsl_keepalive spawned a new process (pid {current_proc.pid}) "
            f"despite existing process (pid {original_pid}) still running"
        )

    def test_xrdp_still_accepting_after_lifecycle(
        self, distro, xrdp_port, rdp_user, production_keepalive,
    ):
        """After both sessions complete, xrdp must still accept connections."""
        r = _run(run_wsl(distro, "systemctl is-active xrdp"))
        assert r.output.strip() == "active", (
            f"xrdp not active after lifecycle test: {r.output.strip()}"
        )
        r = _run(run_wsl(distro, "systemctl is-active xrdp-sesman"))
        assert r.output.strip() == "active", (
            f"xrdp-sesman not active after lifecycle test: {r.output.strip()}"
        )
        _assert_xrdp_accepts_connections(distro, xrdp_port)

    def test_vm_alive_after_all_sessions(self, distro, production_keepalive):
        """The WSL VM must still be alive after all sessions and test cleanup."""
        _assert_wsl_vm_alive(distro)
        assert production_keepalive.poll() is None, (
            "Production keepalive process is no longer running"
        )
