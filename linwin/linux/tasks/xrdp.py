"""xrdp remote desktop setup tasks."""

from __future__ import annotations

from ...shared.subprocess_runner import LineCallback, run_local
from ...shared.task_result import TaskResult
from .apt import APT_ENV, APT_OPTS, is_apt_installed


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
        f"sudo {APT_ENV} apt install -y {APT_OPTS} {XRDP_PACKAGES}", on_line, timeout=1800,
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
        " && grep -q 'XAUTHORITY' /etc/xrdp/startwm.sh 2>/dev/null"
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
    #   - Export XAUTHORITY explicitly: strictly confined snaps (firefox,
    #     chromium) have a remapped HOME, so without the variable they
    #     present no X cookie and fail with "cannot open display".
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
        'export XAUTHORITY="${HOME}/.Xauthority"\n'
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
    # rules.d is mode 750 root:polkitd — an unprivileged test -f cannot
    # see into it and would always report the rule missing.
    check = await run_local(f"sudo test -f {rules_file} && echo yes || echo no", on_line, timeout=30)
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
        " && grep -q 'linwin-x11-dir' /etc/systemd/system/xrdp-sesman.service 2>/dev/null"
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
        "ExecStartPre=-/usr/local/sbin/linwin-x11-dir.sh\n"
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
    """Enable and start the xrdp service.

    Every prerequisite below is required for a working session — a
    failure in any of them must fail the step, not vanish silently.
    """
    prerequisites = [
        # Writable /tmp/.X11-unix so Xorg makes real sockets snaps can use
        ("X11 socket dir", fix_x11_socket_dir),
        # Ensure xrdp can read the TLS key before starting
        ("ssl-cert group", fix_xrdp_ssl_permissions),
        # Create systemd overrides to prevent restart loops
        ("systemd overrides", create_systemd_overrides),
        # Allow colord D-Bus calls so the desktop doesn't crash on interaction
        ("colord polkit rule", configure_colord_polkit),
        # Prevent logind from killing user services prematurely
        ("logind delay", configure_logind_delay),
        # Keep user manager alive even without logind sessions
        ("user linger", enable_user_linger),
        # Prevent GDM from interfering with xrdp sessions
        ("GDM mask", mask_gdm),
    ]
    failures = []
    for name, prerequisite in prerequisites:
        r = await prerequisite(on_line)
        if not r.ok:
            failures.append(f"{name}: {r.message}")
    if failures:
        return TaskResult(ok=False, message="xrdp prerequisites failed — " + "; ".join(failures))

    result = await run_local("sudo systemctl enable --now xrdp", on_line, timeout=120)
    if result.success:
        return TaskResult(ok=True, message="xrdp service enabled and started")
    return TaskResult(ok=False, message="Failed to enable xrdp service")


_X11_FIX_SCRIPT = "/usr/local/sbin/linwin-x11-dir.sh"
_X11_FIX_UNIT = "/etc/systemd/system/linwin-x11-dir.service"


async def fix_x11_socket_dir(on_line: LineCallback | None = None) -> TaskResult:
    """Make /tmp/.X11-unix writable so xrdp's Xorg creates a real socket.

    WSLg mounts /tmp/.X11-unix as a READ-ONLY tmpfs containing only X0,
    so xrdp's Xorg can only bind the abstract socket @/tmp/.X11-unix/X10.
    Snap-confined apps (firefox, chromium) are denied abstract X sockets
    by AppArmor and fail with "cannot open display :10". Replace the
    read-only mount with a writable dir — keeping WSLg's X0 socket
    available through a bind mount — and install a boot-time systemd
    unit so the fix survives WSL restarts.
    """
    check = await run_local(
        "test -w /tmp/.X11-unix"
        " && systemctl is-enabled linwin-x11-dir.service > /dev/null 2>&1"
        " && grep -q 'rebind' " + _X11_FIX_SCRIPT + " 2>/dev/null"
        " && { test -S /tmp/.X11-unix/X0 || ! test -S /mnt/wslg/.X11-unix/X0; }"
        " && echo yes || echo no",
        on_line,
        timeout=30,
    )
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message="X11 socket dir already writable", skipped=True)

    script = (
        f"sudo tee {_X11_FIX_SCRIPT} > /dev/null << 'EOF'\n"
        "#!/bin/sh\n"
        "# linwin: make /tmp/.X11-unix writable so xrdp's Xorg can create a\n"
        "# real socket (snap apps cannot use the abstract fallback), keeping\n"
        "# WSLg's X0 available via a bind mount (rebind when it gets lost).\n"
        "DIR=/tmp/.X11-unix\n"
        "WSLG_X0=/mnt/wslg/.X11-unix/X0\n"
        'if mount | grep -q "on ${DIR} type tmpfs (ro"; then\n'
        '    umount "${DIR}" 2>/dev/null || exit 0\n'
        "fi\n"
        'mkdir -p "${DIR}"\n'
        'chmod 1777 "${DIR}"\n'
        'if [ -S "${WSLG_X0}" ] && [ ! -S "${DIR}/X0" ]; then\n'
        '    umount "${DIR}/X0" 2>/dev/null || true\n'
        '    rm -f "${DIR}/X0"\n'
        '    touch "${DIR}/X0"\n'
        '    mount --bind "${WSLG_X0}" "${DIR}/X0"\n'
        "fi\n"
        "exit 0\n"
        "EOF"
    )
    unit = (
        f"sudo tee {_X11_FIX_UNIT} > /dev/null << 'EOF'\n"
        "[Unit]\n"
        "Description=linwin: writable /tmp/.X11-unix for xrdp + snap apps\n"
        "After=local-fs.target\n"
        "Before=xrdp-sesman.service xrdp.service\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={_X11_FIX_SCRIPT}\n"
        "RemainAfterExit=yes\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
        "EOF"
    )
    r1 = await run_local(script, on_line, timeout=60)
    r2 = await run_local(unit, on_line, timeout=60)
    if not (r1.success and r2.success):
        return TaskResult(ok=False, message="Failed to write the X11 socket dir fix")
    r3 = await run_local(
        f"sudo chmod +x {_X11_FIX_SCRIPT} && sudo systemctl daemon-reload && "
        "sudo systemctl enable linwin-x11-dir.service && "
        "sudo systemctl restart linwin-x11-dir.service",
        on_line,
        timeout=120,
    )
    if r3.success:
        return TaskResult(ok=True, message="X11 socket dir made writable for xrdp sessions")
    return TaskResult(ok=False, message="Failed to enable the X11 socket dir fix service")


# Candidate browser launchers, in preference order, mapped to the XFCE
# helper id that launches them (exo ships /usr/share/xfce4/helpers/<id>.desktop).
_BROWSER_CANDIDATES = [
    ("/snap/bin/firefox", "firefox"),
    ("/usr/bin/firefox", "firefox"),
    ("/snap/bin/chromium", "chromium"),
    ("/usr/bin/chromium-browser", "chromium"),
    ("/usr/bin/google-chrome", "google-chrome"),
]


async def configure_default_browser(on_line: LineCallback | None = None) -> TaskResult:
    """Point the XFCE default Web Browser at an installed browser.

    Ubuntu installs firefox as a snap, which can leave the
    x-www-browser alternative dangling at a /usr/bin/firefox that no
    longer exists and no XFCE preferred browser configured — the
    panel's browser button then fails with "Failed to execute default
    Web Browser". Configure both the XFCE helper and the alternative
    to the first browser actually present; skip when none is installed.
    """
    found_path = found_helper = None
    for path, helper in _BROWSER_CANDIDATES:
        check = await run_local(f"test -x {path} && echo yes || echo no", on_line, timeout=30)
        if check.output.strip() == "yes":
            found_path, found_helper = path, helper
            break
    if not found_path:
        return TaskResult(ok=True, message="No browser installed — nothing to configure", skipped=True)

    check = await run_local(
        f"grep -qx 'WebBrowser={found_helper}' ~/.config/xfce4/helpers.rc 2>/dev/null"
        " && target=$(readlink -f /etc/alternatives/x-www-browser 2>/dev/null)"
        " && test -x \"$target\""
        " && echo yes || echo no",
        on_line,
        timeout=30,
    )
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message=f"Default browser already {found_helper}", skipped=True)

    cmd = (
        "mkdir -p ~/.config/xfce4 && "
        "touch ~/.config/xfce4/helpers.rc && "
        "sed -i '/^WebBrowser=/d' ~/.config/xfce4/helpers.rc && "
        f"echo 'WebBrowser={found_helper}' >> ~/.config/xfce4/helpers.rc && "
        f"sudo update-alternatives --install /usr/bin/x-www-browser x-www-browser {found_path} 200 > /dev/null && "
        f"sudo update-alternatives --set x-www-browser {found_path} > /dev/null"
    )
    result = await run_local(cmd, on_line, timeout=60)
    if result.success:
        return TaskResult(ok=True, message=f"Default browser set to {found_helper} ({found_path})")
    return TaskResult(ok=False, message="Failed to configure default browser")


async def check_xrdp_running(on_line: LineCallback | None = None) -> bool:
    """Check if xrdp service is active."""
    result = await run_local("systemctl is-active xrdp 2>/dev/null", on_line, timeout=30)
    return result.output.strip() == "active"
