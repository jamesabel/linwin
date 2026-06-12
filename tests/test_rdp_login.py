"""Integration test: full RDP login to WSL Ubuntu via xrdp.

Validates the complete RDP stack end-to-end:
 1. xrdp service prerequisites (installed, running, port, session config)
 2. RDP protocol handshake from Windows to the WSL2 VM (X.224 negotiation)
 3. Full NLA authentication via xfreerdp (valid and invalid credentials)
"""

from __future__ import annotations

import socket
import struct

import pytest

from linwin.shared.subprocess_runner import run_wsl

from .helpers import _run, _recv_exact, _cert_flag

# Temporary Linux user created for the RDP auth tests, cleaned up after.
TEST_USER = "_rdptest"
TEST_PASS = "WslRdpTest2024x"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def wsl_ip(distro):
    """Resolve the WSL2 VM IP so Windows-side sockets can reach xrdp."""
    result = _run(run_wsl(distro, "hostname -I"))
    if not result.success or not result.output.strip():
        pytest.skip("Could not determine WSL IP address")
    return result.output.strip().split()[0]


@pytest.fixture(scope="module")
def rdp_test_user(distro):
    """Create a temporary Linux user for RDP auth, remove it after the module."""
    r = _run(run_wsl(
        distro,
        f"id {TEST_USER} &>/dev/null && echo exists || echo missing",
    ))
    if r.output.strip() != "exists":
        r = _run(run_wsl(distro, f"sudo useradd -m -s /bin/bash {TEST_USER}"))
        if not r.success:
            pytest.skip(f"Could not create test user: {r.output}")
    r = _run(run_wsl(
        distro,
        f"echo '{TEST_USER}:{TEST_PASS}' | sudo chpasswd",
    ))
    if not r.success:
        pytest.skip(f"Could not set test user password: {r.output}")
    yield TEST_USER
    _run(run_wsl(distro, f"sudo userdel -r {TEST_USER} 2>/dev/null"))


# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------

class TestRdpPrerequisites:
    """Verify the xrdp infrastructure before attempting a login."""

    def test_wsl_responsive(self, distro):
        result = _run(run_wsl(distro, "echo ready"))
        assert result.success and "ready" in result.output

    def test_xrdp_installed(self, distro):
        result = _run(run_wsl(
            distro,
            "dpkg -l xrdp 2>/dev/null | grep -q '^ii' && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", "xrdp package not installed"

    def test_xfce4_installed(self, distro):
        result = _run(run_wsl(
            distro,
            "dpkg -l xfce4 2>/dev/null | grep -q '^ii' && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", "xfce4 package not installed"

    def test_xrdp_service_active(self, distro):
        result = _run(run_wsl(distro, "systemctl is-active xrdp"))
        assert result.output.strip() == "active", (
            f"xrdp service not active: {result.output.strip()}"
        )

    def test_xrdp_sesman_active(self, distro):
        result = _run(run_wsl(distro, "systemctl is-active xrdp-sesman"))
        assert result.output.strip() == "active", (
            f"xrdp-sesman not active: {result.output.strip()}"
        )

    def test_xrdp_port_configured(self, distro, xrdp_port):
        result = _run(run_wsl(
            distro, "grep -m1 '^port=' /etc/xrdp/xrdp.ini",
        ))
        assert result.output.strip() == f"port={xrdp_port}"

    def test_xrdp_listening(self, distro, xrdp_port):
        result = _run(run_wsl(
            distro, f"ss -tlnp 2>/dev/null | grep ':{xrdp_port} '",
        ))
        assert result.success and str(xrdp_port) in result.output, (
            f"xrdp not listening on port {xrdp_port}"
        )

    def test_startwm_configured_for_xfce4(self, distro):
        result = _run(run_wsl(
            distro,
            "grep -qE 'xfce4-session|startxfce4' /etc/xrdp/startwm.sh && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", (
            "startwm.sh not configured for XFCE4"
        )

    def test_startwm_unsets_dbus(self, distro):
        """startwm.sh must unset DBUS_SESSION_BUS_ADDRESS so XFCE4 creates
        a fresh D-Bus session bus instead of reusing sesman's."""
        result = _run(run_wsl(
            distro,
            "grep -q 'unset DBUS_SESSION_BUS_ADDRESS' /etc/xrdp/startwm.sh && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", (
            "startwm.sh missing 'unset DBUS_SESSION_BUS_ADDRESS' — "
            "RDP sessions will crash immediately after login"
        )

    def test_colord_polkit_rule(self, distro):
        """A polkit rule must allow colord actions without interactive auth.
        Without this, clicking anything in the XFCE desktop triggers a
        colord D-Bus activation that demands polkit auth, which fails
        (no agent in xrdp) and crashes the session.
        Ubuntu 24.04 uses polkit 124+ (JavaScript rules)."""
        # rules.d is mode 750 root:polkitd — must check as root or the
        # file is invisible and this reports a false negative.
        result = _run(run_wsl(
            distro,
            "sudo test -f /etc/polkit-1/rules.d/45-allow-colord.rules"
            " && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", (
            "colord polkit rule missing — RDP sessions will crash on interaction"
        )

    def test_default_browser_launches(self, distro):
        """The XFCE 'Web Browser' launcher must resolve to a real binary.

        Ubuntu installs firefox as a snap, leaving the x-www-browser
        alternative pointing at a /usr/bin/firefox that no longer
        exists — the panel button then fails with 'Failed to execute
        default Web Browser'. Setup must configure a working default
        whenever any browser is installed.
        """
        # Is any browser installed at all? (login shell so /snap/bin is on PATH)
        r = _run(run_wsl(
            distro,
            "bash -lc 'command -v firefox chromium chromium-browser google-chrome' 2>/dev/null | head -1",
        ))
        if not (r.success and r.output.strip()):
            pytest.skip("No browser installed in the distro")

        # exo consults the XFCE helper first; it must name a resolvable browser
        r = _run(run_wsl(
            distro,
            "grep -m1 '^WebBrowser=' ~/.config/xfce4/helpers.rc 2>/dev/null | cut -d= -f2",
        ))
        helper = r.output.strip()
        assert helper, (
            "No default WebBrowser configured in ~/.config/xfce4/helpers.rc — "
            "the XFCE browser button will fail with 'Failed to execute default Web Browser'"
        )
        # The helper id maps to a .desktop in the XFCE helper dirs (XFCE
        # generates user-level ids like firefox_firefox once a browser
        # has been opened); resolve it and check its command exists.
        r = _run(run_wsl(
            distro,
            f"ls ~/.local/share/xfce4/helpers/{helper}.desktop "
            f"/usr/share/xfce4/helpers/{helper}.desktop 2>/dev/null | head -1",
        ))
        helper_file = r.output.strip()
        assert helper_file, (
            f"WebBrowser helper '{helper}' has no .desktop definition in the "
            "XFCE helper directories"
        )
        r = _run(run_wsl(
            distro,
            f"grep -m1 -E '^(TryExec|X-XFCE-Commands)=' '{helper_file}' "
            "| cut -d= -f2 | cut -d';' -f1",
        ))
        command = r.output.strip().split()[0] if r.output.strip() else ""
        assert command, f"Helper file {helper_file} declares no command"
        if command.startswith("/"):
            r = _run(run_wsl(distro, f"test -x {command} && echo yes || echo no"))
        else:
            r = _run(run_wsl(distro, f"bash -lc 'command -v {command} > /dev/null' && echo yes || echo no"))
        assert r.output.strip() == "yes", (
            f"WebBrowser helper '{helper}' resolves to '{command}', which is not executable"
        )

        # The sensible-browser fallback must not be a dangling alternative.
        # test -x follows symlinks, so a dangling target fails it.
        # ($-free on purpose: the wsl.exe relay mangles $ even in quotes.)
        r = _run(run_wsl(
            distro,
            "test -x /etc/alternatives/x-www-browser && echo yes || echo no",
        ))
        assert r.output.strip() == "yes", (
            "x-www-browser alternative is dangling — sensible-browser fallback is broken"
        )

    def test_startwm_exports_xauthority(self, distro):
        """startwm.sh must export XAUTHORITY: strictly confined snaps
        (firefox, chromium) have a remapped HOME and present no X cookie
        without it — failing with 'cannot open display' even when the
        socket is reachable."""
        result = _run(run_wsl(
            distro,
            "grep -q 'export XAUTHORITY' /etc/xrdp/startwm.sh && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", (
            "startwm.sh missing 'export XAUTHORITY' — snap apps cannot "
            "authenticate to the xrdp display"
        )

    def test_startwm_disables_wayland(self, distro):
        """startwm.sh must point WAYLAND_DISPLAY at a nonexistent name.

        Snap firefox probes for WSLg's wayland socket and forces
        GDK_BACKEND=wayland, then fails to open the X display ':10' as
        a wayland socket name. A bogus WAYLAND_DISPLAY defeats the
        probe so GTK falls back to X11.
        """
        result = _run(run_wsl(
            distro,
            "grep -q 'WAYLAND_DISPLAY=xrdp-no-wayland' /etc/xrdp/startwm.sh && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", (
            "startwm.sh missing the WAYLAND_DISPLAY override — snap browsers "
            "will pick the Wayland backend and fail with 'cannot open display'"
        )

    def test_x11_socket_dir_writable(self, distro):
        """/tmp/.X11-unix must be writable for xrdp sessions.

        WSLg mounts it read-only, which forces xrdp's Xorg onto an
        abstract socket that snap-confined apps (firefox, chromium)
        cannot reach — they fail with 'cannot open display :10'.
        """
        r = _run(run_wsl(distro, "test -w /tmp/.X11-unix && echo yes || echo no"))
        assert r.output.strip() == "yes", (
            "/tmp/.X11-unix is read-only — snap apps cannot open the xrdp display"
        )
        r = _run(run_wsl(distro, "systemctl is-enabled linwin-x11-dir.service 2>/dev/null"))
        assert r.output.strip() == "enabled", (
            "linwin-x11-dir.service not enabled — the writable X11 dir won't survive a WSL restart"
        )
        # WSLg's X0 must still be reachable after the remount
        r = _run(run_wsl(distro, "test -S /tmp/.X11-unix/X0 && echo yes || echo no"))
        assert r.output.strip() == "yes", "WSLg X0 socket lost by the X11 dir fix"

    def test_xrdp_in_ssl_cert_group(self, distro):
        result = _run(run_wsl(distro, "id -nG xrdp 2>/dev/null"))
        assert "ssl-cert" in result.output.split(), (
            "xrdp user not in ssl-cert group"
        )

    def test_logind_user_stop_delay(self, distro):
        """UserStopDelaySec must be infinity to prevent logind from killing
        user@UID.service (and the entire XFCE desktop) seconds after login."""
        result = _run(run_wsl(
            distro,
            "grep -q '^UserStopDelaySec=infinity' /etc/systemd/logind.conf"
            " && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", (
            "UserStopDelaySec=infinity not set in logind.conf -- "
            "RDP sessions will die seconds after login"
        )

    def test_user_linger_enabled(self, distro):
        """Linger must be enabled so user@UID.service stays alive even when
        logind doesn't track the xrdp session."""
        # Find the primary non-root user (UID 1000) -- this is the user
        # who will be logging in via RDP.
        result = _run(run_wsl(
            distro,
            "getent passwd 1000 | cut -d: -f1",
        ))
        user = result.output.strip()
        assert user, "No UID 1000 user found"
        result = _run(run_wsl(
            distro,
            f"loginctl show-user {user} 2>/dev/null | grep -c Linger=yes",
        ))
        assert result.output.strip() == "1", (
            f"loginctl linger not enabled for {user} -- user services may be killed"
        )

    def test_gdm_masked(self, distro):
        """GDM must be masked to prevent it from cycling greeter sessions
        that trigger logind power-off in WSL2."""
        result = _run(run_wsl(
            distro,
            "systemctl is-enabled gdm 2>/dev/null; echo rc=$?",
        ))
        output = result.output.strip()
        # masked -> exit 1 with "masked" output; not-found -> exit 1 with empty or error
        assert "masked" in output or "not-found" in output or "No such file" in output, (
            f"GDM is not masked or missing: {output}. "
            "GDM interferes with xrdp sessions in WSL2"
        )


# ---------------------------------------------------------------------------
# 2. RDP protocol handshake (socket-level, from the Windows host)
# ---------------------------------------------------------------------------

class TestRdpProtocolHandshake:
    """Connect from Windows to the WSL2 VM and verify the RDP handshake."""

    def test_tcp_connect(self, wsl_ip, xrdp_port):
        """Raw TCP connection to xrdp succeeds."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((wsl_ip, xrdp_port))
        finally:
            sock.close()

    def test_x224_connection_confirm(self, wsl_ip, xrdp_port):
        """xrdp replies with a valid X.224 Connection Confirm (CC)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        try:
            sock.connect((wsl_ip, xrdp_port))

            # -- Build X.224 Connection Request (CR) ----------------------
            cookie = b"Cookie: mstshash=test\r\n"
            rdp_neg_req = bytes([
                0x01,                       # TYPE_RDP_NEG_REQ
                0x00,                       # flags
                0x08, 0x00,                 # length  (8, LE)
                0x03, 0x00, 0x00, 0x00,     # requestedProtocols: TLS|NLA (LE)
            ])
            variable = cookie + rdp_neg_req

            # X.224 header: LI, type=0xE0 (CR), dst-ref, src-ref, class
            li = 6 + len(variable)
            x224_cr = bytes([
                li, 0xE0,
                0x00, 0x00,     # dst-ref
                0x00, 0x00,     # src-ref
                0x00,           # class
            ]) + variable

            # TPKT wrapper
            tpkt_len = 4 + len(x224_cr)
            tpkt = bytes([0x03, 0x00, (tpkt_len >> 8) & 0xFF, tpkt_len & 0xFF])

            sock.sendall(tpkt + x224_cr)

            # -- Read TPKT response header (4 bytes) ----------------------
            resp_hdr = _recv_exact(sock, 4)
            assert resp_hdr[0] == 3, f"Bad TPKT version: {resp_hdr[0]}"
            resp_len = (resp_hdr[2] << 8) | resp_hdr[3]
            assert resp_len >= 11, f"Response too short: {resp_len} bytes"

            # -- Read X.224 payload ----------------------------------------
            body = _recv_exact(sock, resp_len - 4)

            # byte 1 of body = X.224 type; 0xD0 = Connection Confirm
            assert body[1] == 0xD0, (
                f"Expected X.224 CC (0xD0), got 0x{body[1]:02X}"
            )

            # RDP Negotiation Response starts at offset 7 in body
            if len(body) > 11:
                neg_type = body[7]
                assert neg_type in (0x02, 0x03), (
                    f"Unexpected RDP negotiation type 0x{neg_type:02X}"
                )
                if neg_type == 0x02:  # NEGOTIATION_RSP
                    selected = struct.unpack_from("<I", body, 11)[0]
                    # 0=Standard RDP, 1=TLS, 2=NLA, 3=TLS+NLA
                    assert selected in (0, 1, 2, 3), (
                        f"Unexpected selected protocol: {selected}"
                    )
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# 3. Full RDP authentication (xfreerdp +auth-only from inside WSL)
# ---------------------------------------------------------------------------

class TestRdpFullLogin:
    """Authenticate to xrdp with real credentials via xfreerdp."""

    def test_auth_succeeds(self, distro, xrdp_port, rdp_test_user, xfreerdp_bin):
        """Valid credentials are accepted by xrdp."""
        cert = _cert_flag(xfreerdp_bin)
        cmd = (
            f"{xfreerdp_bin} /v:localhost:{xrdp_port} "
            f"/u:{TEST_USER} /p:{TEST_PASS} "
            f"+auth-only {cert} /log-level:ERROR 2>&1"
        )
        result = _run(run_wsl(distro, cmd))
        assert result.success, (
            f"RDP login failed (exit {result.exit_code}):\n{result.output}"
        )

    def test_auth_output_confirms_success(self, distro, xrdp_port, rdp_test_user, xfreerdp_bin):
        """xfreerdp output explicitly reports 'exit status 0' for valid login."""
        cert = _cert_flag(xfreerdp_bin)
        cmd = (
            f"{xfreerdp_bin} /v:localhost:{xrdp_port} "
            f"/u:{TEST_USER} /p:{TEST_PASS} "
            f"+auth-only {cert} /log-level:ERROR 2>&1"
        )
        result = _run(run_wsl(distro, cmd))
        assert "exit status 0" in result.output, (
            f"Expected 'exit status 0' in output:\n{result.output}"
        )
