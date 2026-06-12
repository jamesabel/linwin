"""Shared test utility functions for RDP test modules."""

from __future__ import annotations

import asyncio
import socket

from linwin.shared.subprocess_runner import run_wsl


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


def _xrdp_connect_hosts(distro: str) -> list[str]:
    """Candidate Windows-side hosts for reaching xrdp inside *distro*.

    The direct VM IP is what production mstsc uses and reaches any
    distro's ports; Windows localhost forwarding is kept as a fallback
    because WSL only provides it for some ports (e.g. it covers the
    real distro's 3390 but not the test clone's 3391).
    """
    hosts = []
    r = _run(run_wsl(distro, "hostname -I"))
    if r.success and r.output.strip():
        hosts.append(r.output.strip().split()[0])
    hosts.append("localhost")
    return hosts


def _assert_xrdp_accepts_connections(distro: str, xrdp_port: int) -> None:
    """Assert xrdp accepts a TCP + X.224 negotiation from Windows.

    Tries the VM IP first, then localhost. Connection refusals move on
    to the next host; once connected, a bad handshake fails immediately.
    """
    hosts = _xrdp_connect_hosts(distro)
    last_error: Exception | None = None
    for host in hosts:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        try:
            sock.connect((host, xrdp_port))
        except OSError as e:
            sock.close()
            last_error = e
            continue
        try:
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
            return
        finally:
            sock.close()
    raise AssertionError(
        f"xrdp not accepting connections on port {xrdp_port} "
        f"(tried {', '.join(hosts)}): {last_error}"
    )


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
