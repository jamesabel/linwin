"""xrdp remote desktop setup tasks."""

from __future__ import annotations

from ...shared.subprocess_runner import LineCallback, run_local
from ...shared.task_result import TaskResult
from .apt import is_apt_installed


async def is_xrdp_installed(on_line: LineCallback | None = None) -> bool:
    """Check if xrdp is installed."""
    return await is_apt_installed("xrdp", on_line)


XRDP_PACKAGES = "xrdp dbus-x11 xfce4 xfce4-terminal"


async def install_xrdp(on_line: LineCallback | None = None) -> TaskResult:
    """Install xrdp, dbus-x11, and xfce4 desktop for RDP sessions.

    GNOME Shell requires 3D acceleration which isn't available over RDP,
    so we use XFCE4 which works reliably with xrdp.
    """
    all_installed = True
    for pkg in XRDP_PACKAGES.split():
        if not await is_apt_installed(pkg, on_line):
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
        timeout=30,
    )
    if check.output.strip() == f"port={port}":
        return TaskResult(ok=True, message=f"xrdp port already {port}", skipped=True)

    # Only change the first uncommented port= line (the global listen port).
    # Session-type sections also have port= lines that must stay as-is.
    result = await run_local(
        f"sudo sed -i '0,/^port=.*/s//port={port}/' /etc/xrdp/xrdp.ini",
        on_line,
        timeout=60,
    )
    if result.success:
        return TaskResult(ok=True, message=f"xrdp port set to {port}")
    return TaskResult(ok=False, message="Failed to configure xrdp port")


async def configure_xrdp_session(on_line: LineCallback | None = None) -> TaskResult:
    """Configure xrdp to launch an XFCE4 session."""
    check = await run_local(
        "grep -q 'unset DBUS_SESSION_BUS_ADDRESS' /etc/xrdp/startwm.sh 2>/dev/null"
        " && grep -q 'XDG_CURRENT_DESKTOP=XFCE' /etc/xrdp/startwm.sh 2>/dev/null"
        " && grep -q 'xfce4-session' /etc/xrdp/startwm.sh 2>/dev/null"
        " && echo yes || echo no",
        on_line,
        timeout=30,
    )
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message="XFCE4 session already configured", skipped=True)

    # Write a clean startwm.sh that launches XFCE4.
    # GNOME Shell requires 3D acceleration not available over RDP.
    # Key fixes:
    #   - Unset DBUS_SESSION_BUS_ADDRESS and XDG_RUNTIME_DIR inherited
    #     from xrdp-sesman so XFCE creates a fresh D-Bus bus.
    #   - Set XDG_CURRENT_DESKTOP=XFCE and DESKTOP_SESSION=xfce
    #     BEFORE sourcing profiles so ubuntu-desktop's GNOME scripts
    #     don't override the desktop environment.
    #   - Disable light-locker (crashes without LightDM).
    #   - Use dbus-launch + exec xfce4-session so sesman tracks the
    #     correct PID (dbus-run-session exits prematurely, causing
    #     sesman to kill the session).
    #   - Log all session output for debugging.
    script = (
        "sudo tee /etc/xrdp/startwm.sh > /dev/null << 'STARTWM'\n"
        "#!/bin/sh\n"
        "exec > /tmp/xrdp-startwm-${USER}.log 2>&1\n"
        "unset DBUS_SESSION_BUS_ADDRESS\n"
        "unset XDG_RUNTIME_DIR\n"
        "if test -r /etc/profile; then\n"
        "\t. /etc/profile\n"
        "fi\n"
        "if test -r ~/.profile; then\n"
        "\t. ~/.profile\n"
        "fi\n"
        "export XDG_SESSION_TYPE=x11\n"
        "export XDG_CURRENT_DESKTOP=XFCE\n"
        "export DESKTOP_SESSION=xfce\n"
        'export XDG_MENU_PREFIX="xfce-"\n'
        'mkdir -p "${HOME}/.config/autostart"\n'
        "printf '[Desktop Entry]\\nHidden=true\\n'"
        ' > "${HOME}/.config/autostart/light-locker.desktop"\n'
        "eval $(dbus-launch --sh-syntax)\n"
        "exec xfce4-session\n"
        "STARTWM"
    )
    result = await run_local(script, on_line, timeout=60)
    if result.success:
        await run_local("sudo chmod +x /etc/xrdp/startwm.sh", on_line, timeout=30)
        return TaskResult(ok=True, message="XFCE4 session configured for xrdp")
    return TaskResult(ok=False, message="Failed to configure xrdp session")


async def configure_colord_polkit(on_line: LineCallback | None = None) -> TaskResult:
    """Allow colord color-management D-Bus calls without interactive auth.

    When an app activates the colord service over D-Bus, PolicyKit demands
    interactive authentication.  There is no polkit agent inside an xrdp
    session, so the request fails and the cascading error crashes the
    desktop.  This rule permits colord actions for any session.

    Ubuntu 24.04 uses polkit 124+ which requires JavaScript rules in
    /etc/polkit-1/rules.d/ (the older .pkla format is not supported).
    """
    rules_file = "/etc/polkit-1/rules.d/45-allow-colord.rules"
    check = await run_local(f"test -f {rules_file} && echo yes || echo no", on_line, timeout=30)
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message="colord polkit rule already present", skipped=True)

    script = (
        f"sudo tee {rules_file} > /dev/null << 'RULES'\n"
        "polkit.addRule(function(action, subject) {\n"
        '    if (action.id.indexOf("org.freedesktop.color-manager.") == 0) {\n'
        "        return polkit.Result.YES;\n"
        "    }\n"
        "});\n"
        "RULES"
    )
    result = await run_local(script, on_line, timeout=60)
    if result.success:
        return TaskResult(ok=True, message="colord polkit rule created")
    return TaskResult(ok=False, message="Failed to create colord polkit rule")


async def fix_xrdp_ssl_permissions(on_line: LineCallback | None = None) -> TaskResult:
    """Add xrdp user to ssl-cert group so it can read the TLS key."""
    # Check if already in the group
    check = await run_local("id -nG xrdp 2>/dev/null", on_line, timeout=30)
    if "ssl-cert" in check.output.split():
        return TaskResult(ok=True, message="xrdp already in ssl-cert group", skipped=True)

    result = await run_local("sudo adduser xrdp ssl-cert", on_line, timeout=60)
    if result.success:
        return TaskResult(ok=True, message="Added xrdp to ssl-cert group")
    return TaskResult(ok=False, message="Failed to add xrdp to ssl-cert group")


async def create_systemd_overrides(on_line: LineCallback | None = None) -> TaskResult:
    """Write full systemd unit replacement files for xrdp and xrdp-sesman.

    We use complete unit file replacements in /etc/systemd/system/ instead
    of drop-in overrides (.service.d/override.conf) because the drop-in
    approach DOES NOT WORK for clearing BindsTo= on systemd 255.  A drop-in
    that sets ``BindsTo=`` (empty) is supposed to reset the list, but
    systemd 255 ignores the reset and keeps the vendor value, causing
    sesman to be yanked down whenever the xrdp socket closes.

    Full replacement files completely supersede the vendor units from
    /lib/systemd/system/ and let us define exactly the directives we want
    without inheriting any unwanted defaults.
    """
    # Check if full replacement files already exist with correct content
    check = await run_local(
        "grep -q 'Type=exec' /etc/systemd/system/xrdp.service 2>/dev/null"
        " && grep -q 'Type=exec' /etc/systemd/system/xrdp-sesman.service 2>/dev/null"
        " && grep -q 'Restart=on-failure' /etc/systemd/system/xrdp.service 2>/dev/null"
        " && grep -q 'Restart=on-failure' /etc/systemd/system/xrdp-sesman.service 2>/dev/null"
        " && echo yes || echo no",
        on_line,
        timeout=30,
    )
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message="systemd unit replacements already configured", skipped=True)

    xrdp_unit = (
        "sudo tee /etc/systemd/system/xrdp.service > /dev/null << 'EOF'\n"
        "[Unit]\n"
        "Description=xrdp daemon\n"
        "After=network.target xrdp-sesman.service\n"
        "Wants=xrdp-sesman.service\n"
        "[Service]\n"
        "Type=exec\n"
        "ExecStartPre=+/bin/sh /usr/share/xrdp/socksetup\n"
        "ExecStart=/usr/sbin/xrdp --nodaemon\n"
        "ExecStop=\n"
        "PIDFile=\n"
        "User=xrdp\n"
        "Group=xrdp\n"
        "RuntimeDirectory=xrdp\n"
        "Restart=on-failure\n"
        "RestartSec=3\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
        "EOF"
    )
    sesman_unit = (
        "sudo tee /etc/systemd/system/xrdp-sesman.service > /dev/null << 'EOF'\n"
        "[Unit]\n"
        "Description=xrdp session manager\n"
        "After=network.target\n"
        "[Service]\n"
        "Type=exec\n"
        "ExecStart=/usr/sbin/xrdp-sesman --nodaemon\n"
        "ExecStop=\n"
        "PIDFile=\n"
        "RuntimeDirectory=xrdp\n"
        "Restart=on-failure\n"
        "RestartSec=3\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
        "EOF"
    )
    r1 = await run_local(xrdp_unit, on_line, timeout=60)
    r2 = await run_local(sesman_unit, on_line, timeout=60)
    if r1.success and r2.success:
        await run_local("sudo systemctl daemon-reload", on_line, timeout=60)
        return TaskResult(ok=True, message="systemd unit replacements created for xrdp")
    return TaskResult(ok=False, message="Failed to create systemd unit replacements")


async def configure_logind_delay(on_line: LineCallback | None = None) -> TaskResult:
    """Set UserStopDelaySec=infinity so logind doesn't kill user services.

    systemd-logind tears down user@UID.service when it thinks the user has
    no active sessions.  xrdp sessions are not always visible to logind,
    so without this setting the user manager (and the entire XFCE desktop)
    gets killed seconds after login.
    """
    check = await run_local(
        "grep -q '^UserStopDelaySec=infinity' /etc/systemd/logind.conf 2>/dev/null"
        " && echo yes || echo no",
        on_line,
        timeout=30,
    )
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message="UserStopDelaySec already set", skipped=True)

    result = await run_local(
        "sudo sed -i 's/^#\\?UserStopDelaySec=.*/UserStopDelaySec=infinity/' /etc/systemd/logind.conf",
        on_line,
        timeout=60,
    )
    if result.success:
        await run_local("sudo systemctl restart systemd-logind", on_line, timeout=60)
        return TaskResult(ok=True, message="UserStopDelaySec set to infinity")
    return TaskResult(ok=False, message="Failed to configure logind delay")


async def enable_user_linger(on_line: LineCallback | None = None) -> TaskResult:
    """Enable loginctl linger for the current user.

    Keeps user@UID.service alive even when no login sessions are tracked
    by logind.  Without this, logind may shut down the user manager
    (killing the XFCE desktop) if the xrdp session is not registered
    as a logind session.
    """
    user = (await run_local("whoami", on_line, timeout=30)).output.strip()
    check = await run_local(f"loginctl show-user {user} 2>/dev/null | grep Linger=yes", on_line, timeout=30)
    if check.success and "Linger=yes" in check.output:
        return TaskResult(ok=True, message=f"Linger already enabled for {user}", skipped=True)

    result = await run_local(f"loginctl enable-linger {user}", on_line, timeout=30)
    if result.success:
        return TaskResult(ok=True, message=f"Linger enabled for {user}")
    return TaskResult(ok=False, message=f"Failed to enable linger for {user}")


async def mask_gdm(on_line: LineCallback | None = None) -> TaskResult:
    """Mask GDM so it cannot start and interfere with xrdp sessions.

    GDM (installed via ubuntu-desktop) tries to run a greeter on display :0
    but there is no physical display in WSL2.  It cycles through sessions
    that immediately fail, eventually triggering systemd-logind to issue
    'The system will power off now!' which kills everything.
    """
    check = await run_local("systemctl is-enabled gdm 2>/dev/null", on_line, timeout=30)
    status = check.output.strip()
    if status == "masked":
        return TaskResult(ok=True, message="GDM already masked", skipped=True)
    if status in ("not-found", "") or "No such file" in check.output:
        return TaskResult(ok=True, message="GDM not installed", skipped=True)

    result = await run_local("sudo systemctl mask gdm", on_line, timeout=60)
    if result.success:
        # Also stop it if it's currently running
        await run_local("sudo systemctl stop gdm 2>/dev/null", on_line, timeout=60)
        return TaskResult(ok=True, message="GDM masked")
    return TaskResult(ok=False, message="Failed to mask GDM")


async def enable_xrdp_service(on_line: LineCallback | None = None) -> TaskResult:
    """Enable and start the xrdp service."""
    # Ensure xrdp can read the TLS key before starting
    await fix_xrdp_ssl_permissions(on_line)
    # Create systemd overrides to prevent restart loops
    await create_systemd_overrides(on_line)
    # Allow colord D-Bus calls so the desktop doesn't crash on interaction
    await configure_colord_polkit(on_line)
    # Prevent logind from killing user services prematurely
    await configure_logind_delay(on_line)
    # Keep user manager alive even without logind sessions
    await enable_user_linger(on_line)
    # Prevent GDM from interfering with xrdp sessions
    await mask_gdm(on_line)

    result = await run_local("sudo systemctl enable --now xrdp", on_line, timeout=120)
    if result.success:
        return TaskResult(ok=True, message="xrdp service enabled and started")
    return TaskResult(ok=False, message="Failed to enable xrdp service")


async def check_xrdp_running(on_line: LineCallback | None = None) -> bool:
    """Check if xrdp service is active."""
    result = await run_local("systemctl is-active xrdp 2>/dev/null", on_line, timeout=30)
    return result.output.strip() == "active"
