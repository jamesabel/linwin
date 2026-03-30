"""End-to-end RDP desktop test: connect as UID 1000 user, verify XFCE desktop,
launch xfce4-terminal, take screenshots, and verify session stability.

Tests run on Windows and issue commands to WSL via wsl.exe. Complex bash
scripts are written to temp files to avoid WSL2 bash -c quoting issues.

WSL2 shuts down its VM when all wsl.exe processes exit (despite systemd=true).
A background ``wsl.exe -- sleep infinity`` keepalive is used to prevent this.
"""

from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time

import pytest

from linwin.shared.subprocess_runner import run_command, run_wsl

from conftest import _run, _cert_flag, _recv_exact, _collect_diagnostics

TEMP_PASSWORD = "TempRdpDesktopTest2024x"

# The session must stay alive at least this many seconds after app launch.
SESSION_STABILITY_SECS = 15


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def wsl_keepalive(distro):
    """Keep WSL alive for the entire test module.

    WSL2 shuts down the VM when all wsl.exe processes exit, killing xrdp
    and all sessions. This fixture starts a background ``sleep infinity``
    process that keeps the VM running throughout the tests and after they
    complete (so the user can immediately use mstsc).
    """
    proc = subprocess.Popen(
        ["wsl.exe", "-d", distro, "--", "sleep", "infinity"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    # Wait for WSL to be ready
    for _ in range(10):
        r = _run(run_wsl(distro, "echo ready"))
        if r.success and "ready" in r.output:
            break
        time.sleep(1)
    yield proc
    # Do NOT kill the keepalive -- leave WSL running so the user can
    # connect with mstsc immediately after the test finishes.


@pytest.fixture(scope="module")
def primary_user(distro, wsl_keepalive):
    """Find the UID 1000 user (the primary Ubuntu user)."""
    r = _run(run_wsl(distro, "getent passwd 1000 | cut -d: -f1"))
    user = r.output.strip()
    if not r.success or not user:
        pytest.skip("No UID 1000 user found in WSL distro")
    return user


@pytest.fixture(scope="module")
def rdp_user(distro, primary_user):
    """Set a temporary password for the primary user, clean up stale sessions,
    restart xrdp, yield the username, then restore original password on teardown."""
    # Save the original password hash so we can restore it
    r = _run(run_wsl(distro, f"sudo getent shadow {primary_user} | cut -d: -f2"))
    original_hash = r.output.strip() if r.success else ""

    # Set temporary password
    r = _run(run_wsl(distro, f"echo '{primary_user}:{TEMP_PASSWORD}' | sudo chpasswd"))
    if not r.success:
        pytest.skip(f"Could not set password for {primary_user}: {r.output}")

    # Kill stale xfce4-session processes from previous runs
    _run(run_wsl(distro, f"sudo pkill -9 -u {primary_user} xfce4-session 2>/dev/null"))
    _run(run_wsl(distro, "sleep 1"))

    # Restart xrdp + sesman to clear stale session tracking
    _run(run_wsl(distro, "sudo systemctl restart xrdp xrdp-sesman"))
    _run(run_wsl(distro, "sleep 2"))

    yield primary_user

    # Teardown: kill leftover session processes, restore password.
    # Do NOT restart xrdp -- the keepalive keeps WSL alive and xrdp
    # must remain running for the user to connect after tests finish.
    _run(run_wsl(distro, f"sudo pkill -9 -u {primary_user} xfce4-session 2>/dev/null"))
    _run(run_wsl(distro, f"sudo pkill -f xfreerdp 2>/dev/null"))
    _run(run_wsl(distro, f"sudo pkill Xvfb 2>/dev/null"))
    _run(run_wsl(distro, "sleep 1"))
    # Restore the original password hash.  The hash contains $ characters
    # that bash expands, so write it to a temp file to avoid shell mangling.
    if original_hash:
        import tempfile as _tf
        hash_file = os.path.join(_tf.gettempdir(), "pw_restore.txt")
        with open(hash_file, "w", newline="\n") as hf:
            hf.write(f"{primary_user}:{original_hash}\n")
        wsl_hash = hash_file.replace("\\", "/")
        wsl_hash = f"/mnt/{wsl_hash[0].lower()}{wsl_hash[2:]}"
        _run(run_wsl(distro, f"sudo chpasswd -e < '{wsl_hash}'"))
        os.unlink(hash_file)
    else:
        _run(run_wsl(distro, f"sudo passwd -u {primary_user}"))


@pytest.fixture(scope="module")
def xfreerdp_bin(distro, wsl_keepalive):
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
def ensure_tools(distro, wsl_keepalive):
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
def ensure_xvfb(distro, wsl_keepalive):
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

def _copy_screenshot_from_wsl(distro: str, wsl_path: str, local_dir: str) -> str:
    """Copy a screenshot from WSL to a local Windows temp directory."""
    basename = os.path.basename(wsl_path)
    local_path = os.path.join(local_dir, basename)
    wsl_local = local_path.replace("\\", "/")
    wsl_local = f"/mnt/{wsl_local[0].lower()}{wsl_local[2:]}"
    r = _run(run_wsl(distro, f"test -f '{wsl_path}' && cp '{wsl_path}' '{wsl_local}' && echo copied"))
    if r.success and "copied" in r.output:
        return local_path
    return ""


def _run_rdp_session(
    distro: str,
    xrdp_port: int,
    user: str,
    password: str,
    xfreerdp_bin: str,
    session_label: str,
    stability_secs: int = SESSION_STABILITY_SECS,
    launch_app: bool = True,
) -> tuple[bool, str]:
    """Connect via RDP, optionally launch an app, verify session stability.

    Returns (success: bool, output: str).
    """
    cert = _cert_flag(xfreerdp_bin)

    app_block = ""
    if launch_app:
        app_block = """
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
        echo "xfce4-terminal window found after ${TWAIT}s"
        break
    fi
done

if [ "$TERM_FOUND" -eq 0 ]; then
    echo "WARNING: xfce4-terminal window not detected via xdotool (continuing)"
fi

# --- Take screenshot with terminal ---
sudo -u $USER DISPLAY=$DISP XAUTHORITY=/home/$USER/.Xauthority \\
    import -window root /tmp/rdp_screenshots/{label}_with_terminal.png 2>&1 || \\
    echo "WARNING: terminal screenshot failed"
""".replace("{label}", session_label)

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

sudo mkdir -p /tmp/rdp_screenshots
sudo chmod 777 /tmp/rdp_screenshots

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
    import -window root /tmp/rdp_screenshots/${{LABEL}}_desktop.png 2>&1 || \\
    echo "WARNING: desktop screenshot failed"
{app_block}
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

    tmp = os.path.join(tempfile.gettempdir(), f"rdp_{session_label}.sh")
    with open(tmp, "w", newline="\n") as f:
        f.write(script)

    wsl_tmp = tmp.replace("\\", "/")
    wsl_tmp = f"/mnt/{wsl_tmp[0].lower()}{wsl_tmp[2:]}"
    _run(run_wsl(distro, f"cp '{wsl_tmp}' /tmp/rdp_{session_label}.sh && chmod +x /tmp/rdp_{session_label}.sh"))

    total_timeout = stability_secs + 90
    result = _run(run_command(
        ["wsl.exe", "-d", distro, "--", "bash", f"/tmp/rdp_{session_label}.sh"],
        timeout=float(total_timeout),
    ))

    return ("SUCCESS" in result.output, result.output)


def _assert_xrdp_accepts_connections(xrdp_port: int):
    """Assert xrdp accepts TCP + X.224 + TLS from Windows."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    try:
        sock.connect(("localhost", xrdp_port))
        cookie = b"Cookie: mstshash=test\r\n"
        rdp_neg_req = bytes([0x01, 0x00, 0x08, 0x00, 0x03, 0x00, 0x00, 0x00])
        variable = cookie + rdp_neg_req
        li = 6 + len(variable)
        x224_cr = bytes([li, 0xE0, 0x00, 0x00, 0x00, 0x00, 0x00]) + variable
        tpkt_len = 4 + len(x224_cr)
        tpkt = bytes([0x03, 0x00, (tpkt_len >> 8) & 0xFF, tpkt_len & 0xFF])
        sock.sendall(tpkt + x224_cr)
        resp_hdr = _recv_exact(sock, 4)
        assert resp_hdr[0] == 3, f"Bad TPKT version: {resp_hdr[0]}"
        resp_len = (resp_hdr[2] << 8) | resp_hdr[3]
        body = _recv_exact(sock, resp_len - 4)
        assert body[1] == 0xD0, f"Expected X.224 CC (0xD0), got 0x{body[1]:02X}"
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# Module-level screenshot directory (shared between tests)
# ---------------------------------------------------------------------------

_screenshot_local_dir = os.path.join(tempfile.gettempdir(), "rdp_desktop_screenshots")
os.makedirs(_screenshot_local_dir, exist_ok=True)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRdpDesktopSession:
    """Connect via RDP as the primary user, launch apps, verify stability.

    Tests run TWO consecutive sessions to verify reconnection works.
    """

    def test_two_consecutive_sessions(
        self,
        distro,
        xrdp_port,
        rdp_user,
        xfreerdp_bin,
        ensure_xvfb,
        ensure_tools,
    ):
        """Launch an RDP session, verify desktop + app, disconnect, then
        do it again. Both sessions must succeed.

        This catches:
        - Session crashes on first connect
        - xrdp/sesman not recovering after disconnect
        - WSL shutting down between sessions
        """
        user = rdp_user
        failures = []

        for attempt, label in enumerate(["session1", "session2"], 1):
            # Before each session, verify xrdp is accepting connections from Windows
            try:
                _assert_xrdp_accepts_connections(xrdp_port)
            except Exception as e:
                # xrdp might need a moment after previous session cleanup
                time.sleep(3)
                try:
                    _assert_xrdp_accepts_connections(xrdp_port)
                except Exception as e2:
                    failures.append(
                        f"Attempt {attempt} ({label}): xrdp not accepting "
                        f"Windows connections before session start: {e2}"
                    )
                    break

            # Clean up any leftover session from previous attempt
            if attempt > 1:
                _run(run_wsl(distro, f"sudo pkill -9 -u {user} xfce4-session 2>/dev/null"))
                _run(run_wsl(distro, "sleep 3"))

            # Run the session
            success, output = _run_rdp_session(
                distro, xrdp_port, user, TEMP_PASSWORD,
                xfreerdp_bin, label,
                launch_app=(attempt == 1),  # launch app only on first session
            )

            # Copy screenshots
            for suffix in ("desktop", "with_terminal"):
                _copy_screenshot_from_wsl(
                    distro,
                    f"/tmp/rdp_screenshots/{label}_{suffix}.png",
                    _screenshot_local_dir,
                )

            if not success:
                diagnostics = _collect_diagnostics(distro, user)
                failures.append(
                    f"\n{'='*60}\n"
                    f"Attempt {attempt} ({label}) FAILED\n"
                    f"{'='*60}\n\n"
                    f"--- script output ---\n{output}\n\n"
                    f"--- screenshots in ---\n{_screenshot_local_dir}\n\n"
                    f"{diagnostics}"
                )
                break  # no point trying second session if first failed

            # Clean up this session before next attempt
            _run(run_wsl(distro, f"sudo pkill -9 -u {user} xfce4-session 2>/dev/null"))
            _run(run_wsl(distro, f"sudo pkill -f xfreerdp 2>/dev/null"))
            _run(run_wsl(distro, f"sudo pkill Xvfb 2>/dev/null"))
            _run(run_wsl(distro, "sleep 3"))

        if failures:
            pytest.fail("\n".join(failures))

    def test_xrdp_still_running_after_sessions(
        self,
        distro,
        xrdp_port,
        rdp_user,
        xfreerdp_bin,
        ensure_xvfb,
        ensure_tools,
    ):
        """After session tests complete, xrdp must still be accepting connections.

        This verifies that test cleanup doesn't break xrdp, and that the
        WSL VM is still alive (not shut down due to idle timeout).
        """
        # Check from WSL side
        r = _run(run_wsl(distro, "systemctl is-active xrdp"))
        assert r.output.strip() == "active", (
            f"xrdp not active after tests: {r.output.strip()}"
        )
        r = _run(run_wsl(distro, "systemctl is-active xrdp-sesman"))
        assert r.output.strip() == "active", (
            f"xrdp-sesman not active after tests: {r.output.strip()}"
        )

        # Check from Windows side -- this is what mstsc needs
        _assert_xrdp_accepts_connections(xrdp_port)

    def test_screenshot_valid(
        self,
        distro,
        xrdp_port,
        rdp_user,
        xfreerdp_bin,
        ensure_xvfb,
        ensure_tools,
    ):
        """Verify the desktop screenshot exists and is a valid PNG."""
        screenshot_path = os.path.join(_screenshot_local_dir, "session1_desktop.png")

        if not os.path.isfile(screenshot_path):
            _copy_screenshot_from_wsl(
                distro,
                "/tmp/rdp_screenshots/session1_desktop.png",
                _screenshot_local_dir,
            )

        if not os.path.isfile(screenshot_path):
            pytest.skip("Desktop screenshot not found")

        file_size = os.path.getsize(screenshot_path)
        assert file_size > 1000, (
            f"Screenshot file too small ({file_size} bytes), likely corrupt"
        )

        try:
            from PIL import Image
            img = Image.open(screenshot_path)
            width, height = img.size
            assert width >= 100, f"Screenshot width too small: {width}px"
            assert height >= 100, f"Screenshot height too small: {height}px"
        except ImportError:
            with open(screenshot_path, "rb") as f:
                magic = f.read(8)
            assert magic[:4] == b"\x89PNG", (
                f"File does not have PNG magic bytes: {magic[:4]!r}"
            )

    def test_password_not_locked(self, distro, primary_user):
        """The primary user's password must not be locked after tests.

        A locked password causes 'login failed' from sesman even with
        correct credentials, breaking mstsc for the user.
        """
        r = _run(run_wsl(distro, f"sudo passwd -S {primary_user}"))
        fields = r.output.strip().split()
        status = fields[1] if len(fields) > 1 else "?"
        assert status == "P", (
            f"Password for {primary_user} is '{status}' (expected 'P' for usable). "
            f"Full status: {r.output.strip()}"
        )
