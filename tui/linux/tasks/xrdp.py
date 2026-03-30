"""xrdp remote desktop setup tasks."""

from __future__ import annotations

from ...shared.subprocess_runner import LineCallback, run_local
from ...shared.task_result import TaskResult


async def is_xrdp_installed(on_line: LineCallback | None = None) -> bool:
    """Check if xrdp is installed."""
    result = await run_local(
        "dpkg -l xrdp 2>/dev/null | grep -q '^ii' && echo yes || echo no",
        on_line,
    )
    return result.output.strip() == "yes"


XRDP_PACKAGES = "xrdp dbus-x11 xfce4"


async def install_xrdp(on_line: LineCallback | None = None) -> TaskResult:
    """Install xrdp, dbus-x11, and xfce4 desktop for RDP sessions.

    GNOME Shell requires 3D acceleration which isn't available over RDP,
    so we use XFCE4 which works reliably with xrdp.
    """
    all_installed = True
    for pkg in XRDP_PACKAGES.split():
        check = await run_local(
            f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii' && echo yes || echo no",
            on_line,
        )
        if check.output.strip() != "yes":
            all_installed = False
            break
    if all_installed:
        return TaskResult(ok=True, message="xrdp packages already installed", skipped=True)

    result = await run_local(
        f"sudo apt install -y {XRDP_PACKAGES}", on_line, timeout=1800,
    )
    if result.success:
        return TaskResult(ok=True, message="xrdp and xfce4 installed")
    return TaskResult(ok=False, message="Failed to install xrdp packages")


async def configure_xrdp_port(port: int = 3390, on_line: LineCallback | None = None) -> TaskResult:
    """Set xrdp listen port in /etc/xrdp/xrdp.ini."""
    # Check if the first uncommented port= line already has the desired port
    check = await run_local(
        f"grep -m1 '^port=' /etc/xrdp/xrdp.ini 2>/dev/null",
        on_line,
    )
    if check.output.strip() == f"port={port}":
        return TaskResult(ok=True, message=f"xrdp port already {port}", skipped=True)

    # Only change the first uncommented port= line (the global listen port).
    # Session-type sections also have port= lines that must stay as-is.
    result = await run_local(
        f"sudo sed -i '0,/^port=.*/s//port={port}/' /etc/xrdp/xrdp.ini",
        on_line,
    )
    if result.success:
        return TaskResult(ok=True, message=f"xrdp port set to {port}")
    return TaskResult(ok=False, message="Failed to configure xrdp port")


async def configure_xrdp_session(on_line: LineCallback | None = None) -> TaskResult:
    """Configure xrdp to launch an XFCE4 session."""
    check = await run_local(
        "grep -q 'startxfce4' /etc/xrdp/startwm.sh 2>/dev/null && echo yes || echo no",
        on_line,
    )
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message="XFCE4 session already configured", skipped=True)

    # Write a clean startwm.sh that launches XFCE4.
    # GNOME Shell requires 3D acceleration not available over RDP.
    script = (
        "sudo tee /etc/xrdp/startwm.sh > /dev/null << 'STARTWM'\n"
        "#!/bin/sh\n"
        "if test -r /etc/profile; then\n"
        "\t. /etc/profile\n"
        "fi\n"
        "if test -r ~/.profile; then\n"
        "\t. ~/.profile\n"
        "fi\n"
        "export XDG_SESSION_TYPE=x11\n"
        "exec startxfce4\n"
        "STARTWM"
    )
    result = await run_local(script, on_line)
    if result.success:
        await run_local("sudo chmod +x /etc/xrdp/startwm.sh", on_line)
        return TaskResult(ok=True, message="XFCE4 session configured for xrdp")
    return TaskResult(ok=False, message="Failed to configure xrdp session")


async def fix_xrdp_ssl_permissions(on_line: LineCallback | None = None) -> TaskResult:
    """Add xrdp user to ssl-cert group so it can read the TLS key."""
    # Check if already in the group
    check = await run_local("id -nG xrdp 2>/dev/null", on_line)
    if "ssl-cert" in check.output.split():
        return TaskResult(ok=True, message="xrdp already in ssl-cert group", skipped=True)

    result = await run_local("sudo adduser xrdp ssl-cert", on_line)
    if result.success:
        return TaskResult(ok=True, message="Added xrdp to ssl-cert group")
    return TaskResult(ok=False, message="Failed to add xrdp to ssl-cert group")


async def create_systemd_overrides(on_line: LineCallback | None = None) -> TaskResult:
    """Create systemd overrides to prevent PID file race conditions.

    xrdp and xrdp-sesman use Type=forking with PID files by default.
    Systemd can't always find the PID file in time, causing restart loops.
    We override both to Type=exec with --nodaemon. Also clears the
    BindsTo/StopWhenUnneeded on sesman that causes cascading failures.
    """
    xrdp_override = (
        "sudo mkdir -p /etc/systemd/system/xrdp.service.d && "
        "sudo tee /etc/systemd/system/xrdp.service.d/override.conf > /dev/null << 'EOF'\n"
        "[Unit]\n"
        "Requires=\n"
        "Wants=xrdp-sesman.service\n"
        "[Service]\n"
        "Type=exec\n"
        "ExecStart=\n"
        "ExecStart=/usr/sbin/xrdp --nodaemon\n"
        "PIDFile=\n"
        "EOF"
    )
    sesman_override = (
        "sudo mkdir -p /etc/systemd/system/xrdp-sesman.service.d && "
        "sudo tee /etc/systemd/system/xrdp-sesman.service.d/override.conf > /dev/null << 'EOF'\n"
        "[Unit]\n"
        "BindsTo=\n"
        "StopWhenUnneeded=false\n"
        "[Service]\n"
        "Type=exec\n"
        "ExecStart=\n"
        "ExecStart=/usr/sbin/xrdp-sesman --nodaemon\n"
        "PIDFile=\n"
        "EOF"
    )
    r1 = await run_local(xrdp_override, on_line)
    r2 = await run_local(sesman_override, on_line)
    if r1.success and r2.success:
        await run_local("sudo systemctl daemon-reload", on_line)
        return TaskResult(ok=True, message="systemd overrides created for xrdp")
    return TaskResult(ok=False, message="Failed to create systemd overrides")


async def enable_xrdp_service(on_line: LineCallback | None = None) -> TaskResult:
    """Enable and start the xrdp service."""
    # Ensure xrdp can read the TLS key before starting
    await fix_xrdp_ssl_permissions(on_line)
    # Create systemd overrides to prevent restart loops
    await create_systemd_overrides(on_line)

    result = await run_local("sudo systemctl enable --now xrdp", on_line)
    if result.success:
        return TaskResult(ok=True, message="xrdp service enabled and started")
    return TaskResult(ok=False, message="Failed to enable xrdp service")


async def check_xrdp_running(on_line: LineCallback | None = None) -> bool:
    """Check if xrdp service is active."""
    result = await run_local("systemctl is-active xrdp 2>/dev/null", on_line)
    return result.output.strip() == "active"
