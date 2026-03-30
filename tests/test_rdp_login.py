"""Integration test: full RDP login to WSL Ubuntu via xrdp.

Validates the complete RDP stack end-to-end:
 1. xrdp service prerequisites (installed, running, port, session config)
 2. RDP protocol handshake from Windows to the WSL2 VM (X.224 negotiation)
 3. Full NLA authentication via xfreerdp (valid and invalid credentials)
"""

from __future__ import annotations

import asyncio
import socket
import struct
from pathlib import Path

import pytest

from tui.shared.config import load_config
from tui.shared.subprocess_runner import run_wsl

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

# Temporary Linux user created for the RDP auth tests, cleaned up after.
TEST_USER = "_rdptest"
TEST_PASS = "WslRdpTest2024x"


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


@pytest.fixture(scope="module")
def xfreerdp_bin(distro):
    """Return the xfreerdp binary name, installing it if necessary."""
    for binary in ("xfreerdp3", "xfreerdp"):
        r = _run(run_wsl(distro, f"which {binary} 2>/dev/null"))
        if r.success and r.output.strip():
            return binary
    r = _run(run_wsl(distro, "sudo apt-get install -y freerdp2-x11 2>&1"))
    if r.success:
        return "xfreerdp"
    pytest.skip("xfreerdp not available and could not be installed")


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
            "grep -q 'startxfce4' /etc/xrdp/startwm.sh && echo yes || echo no",
        ))
        assert result.output.strip() == "yes", (
            "startwm.sh not configured for XFCE4"
        )

    def test_xrdp_in_ssl_cert_group(self, distro):
        result = _run(run_wsl(distro, "id -nG xrdp 2>/dev/null"))
        assert "ssl-cert" in result.output.split(), (
            "xrdp user not in ssl-cert group"
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

    @staticmethod
    def _cert_flag(binary: str) -> str:
        """Return the correct cert-ignore flag for the freerdp version."""
        return "/cert:ignore" if binary == "xfreerdp3" else "/cert-ignore"

    def test_auth_succeeds(self, distro, xrdp_port, rdp_test_user, xfreerdp_bin):
        """Valid credentials are accepted by xrdp."""
        cert = self._cert_flag(xfreerdp_bin)
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
        cert = self._cert_flag(xfreerdp_bin)
        cmd = (
            f"{xfreerdp_bin} /v:localhost:{xrdp_port} "
            f"/u:{TEST_USER} /p:{TEST_PASS} "
            f"+auth-only {cert} /log-level:ERROR 2>&1"
        )
        result = _run(run_wsl(distro, cmd))
        assert "exit status 0" in result.output, (
            f"Expected 'exit status 0' in output:\n{result.output}"
        )
