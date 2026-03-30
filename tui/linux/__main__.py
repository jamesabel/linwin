#!/usr/bin/env python3
"""Linux-side TUI entry point for WSL Ubuntu setup.

Usage:
    python3 -m tui.linux                                       # Interactive TUI
    python3 -m tui.linux --headless --step enable-systemd      # Headless: enable systemd
    python3 -m tui.linux --headless --step install-packages    # Headless: install packages
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

from ..shared.setup_logging import setup_logging


def find_config() -> dict:
    """Find and load config.json."""
    project_root = Path(__file__).resolve().parent.parent.parent
    config_path = project_root / "config.json"
    if not config_path.exists():
        print(f"ERROR:config.json not found at {config_path}", flush=True)
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


# ---------- Headless mode (no textual import) ----------

_log = logging.getLogger("wslsetup")


def headless_task(task_id: str, status: str) -> None:
    _log.info("TASK %-25s -> %s", task_id, status)
    print(f"TASK:{task_id}:{status}", flush=True)


def headless_log(msg: str) -> None:
    _log.info("LOG: %s", msg)
    print(f"LOG:{msg}", flush=True)


def headless_error(msg: str) -> None:
    _log.error("ERROR: %s", msg)
    print(f"ERROR:{msg}", flush=True)


def run_cmd(cmd: str) -> tuple[int, str]:
    """Run a shell command synchronously, streaming output to avoid buffering.

    Uses Popen with line-by-line reading instead of subprocess.run with
    capture_output to prevent memory buildup during large installs (snaps).
    Only the last 50 lines are kept for the return value.
    """
    import subprocess
    _log.info("RUN: %s", cmd)
    tail: list[str] = []
    max_tail = 50
    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True,
        )
        for line in proc.stdout:
            line = line.rstrip("\n\r")
            _log.debug("  | %s", line)
            tail.append(line)
            if len(tail) > max_tail:
                tail.pop(0)
        proc.wait()
    except Exception as exc:
        _log.error("run_cmd exception: %s", exc)
        return 1, str(exc)
    output = "\n".join(tail)
    if proc.returncode == 0:
        _log.info("OK  (exit=0): %s", cmd)
    else:
        _log.warning("FAIL (exit=%d): %s", proc.returncode, cmd)
    return proc.returncode, output


def headless_enable_systemd(config: dict) -> int:
    """Enable systemd in wsl.conf. Delegates to the async implementation in tasks.systemd."""
    from .tasks.systemd import enable_systemd

    headless_task("enable_systemd", "running")
    result = asyncio.run(enable_systemd())

    if result.skipped:
        headless_task("enable_systemd", "done")
        headless_log("systemd already enabled in wsl.conf.")
    elif result.ok:
        headless_task("enable_systemd", "done")
        headless_log("systemd enabled. WSL restart required.")
    else:
        headless_task("enable_systemd", "failed")
        headless_error(f"Failed to enable systemd: {result.message}")
        return 1
    return 0


def headless_install_packages(config: dict) -> int:
    """Install apt packages, snaps, verify WSLg."""
    exit_code = 0

    # apt update
    headless_task("apt_update", "running")
    headless_log("Running apt update...")
    rc, out = run_cmd("sudo apt update -y 2>&1")
    headless_task("apt_update", "done" if rc == 0 else "failed")
    if rc != 0:
        headless_error(f"apt update failed: {out}")

    # apt upgrade
    headless_task("apt_upgrade", "running")
    headless_log("Running apt upgrade...")
    rc, out = run_cmd("sudo apt upgrade -y 2>&1")
    headless_task("apt_upgrade", "done" if rc == 0 else "failed")

    # apt packages
    for pkg in config.get("aptPackages", []):
        tid = f"apt_{pkg}"
        headless_task(tid, "running")

        rc, out = run_cmd(f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii' && echo yes || echo no")
        if out.strip() == "yes":
            headless_task(tid, "done")
            headless_log(f"{pkg} already installed.")
            continue

        headless_log(f"Installing {pkg}...")
        rc, out = run_cmd(f"sudo apt install -y {pkg} 2>&1")
        headless_task(tid, "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to install {pkg}: {out}")
            exit_code = 1

    # Setup snapd
    headless_task("setup_snapd", "running")
    headless_log("Setting up snapd...")

    rc, out = run_cmd("systemctl is-system-running 2>/dev/null")
    if out.strip() not in ("running", "degraded"):
        headless_task("setup_snapd", "failed")
        headless_error("systemd not running. Snaps require systemd + WSL restart.")
        exit_code = 1
    else:
        run_cmd("sudo systemctl enable --now snapd.socket 2>/dev/null")
        run_cmd("sudo systemctl enable --now snapd 2>/dev/null")
        run_cmd("sudo snap wait system seed.loaded 2>/dev/null || sleep 5")
        headless_task("setup_snapd", "done")

        # Install snaps
        for snap_info in config.get("snaps", []):
            name = snap_info["name"]
            classic = snap_info.get("classic", False)
            tid = f"snap_{name}"
            headless_task(tid, "running")

            rc, out = run_cmd(f"snap list {name} 2>/dev/null && echo yes || echo no")
            if "yes" in out:
                headless_task(tid, "done")
                headless_log(f"{name} already installed.")
                continue

            flags = "--classic" if classic else ""
            headless_log(f"Installing snap: {name}...")
            rc, out = run_cmd(f"sudo snap install {flags} {name} 2>&1")
            if rc != 0 and "change in progress" in out:
                # A previous install may still be running in snapd.
                # Wait for it to finish, then check if it succeeded.
                headless_log(f"Snap change in progress for {name}, waiting...")
                import time
                for attempt in range(6):
                    time.sleep(10)
                    chk_rc, chk_out = run_cmd(f"snap list {name} 2>/dev/null && echo yes || echo no")
                    if "yes" in chk_out:
                        headless_log(f"{name} installed by background change.")
                        rc = 0
                        break
                    headless_log(f"Still waiting for {name} (attempt {attempt + 1}/6)...")
                else:
                    # Last resort: abort stuck changes and retry
                    headless_log(f"Aborting stuck snap changes for {name}...")
                    run_cmd(
                        f"snap changes 2>/dev/null | grep -i '{name}' | grep -v Done "
                        "| awk '{{print $1}}' | while read cid; do sudo snap abort $cid 2>&1; done"
                    )
                    time.sleep(2)
                    headless_log(f"Retrying snap install: {name}...")
                    rc, out = run_cmd(f"sudo snap install {flags} {name} 2>&1")
            headless_task(tid, "done" if rc == 0 else "failed")
            if rc != 0:
                headless_error(f"Failed to install {name}: {out}")
                exit_code = 1

    # Verify WSLg
    headless_task("verify_wslg", "running")
    display = os.environ.get("DISPLAY", "")
    wslg_dir = os.path.isdir("/mnt/wslg")
    headless_log(f"DISPLAY={display or '(not set)'}")
    headless_log(f"/mnt/wslg: {'exists' if wslg_dir else 'not found'}")
    wslg_ok = bool(display) and wslg_dir
    headless_task("verify_wslg", "done" if wslg_ok else "failed")

    return exit_code


def headless_configure_xrdp(config: dict) -> int:
    """Install xrdp + xfce4, configure port/session, enable service.

    GNOME Shell requires 3D acceleration which isn't available over RDP,
    so we use XFCE4 which works reliably with xrdp.
    """
    exit_code = 0
    port = config.get("xrdpPort", 3390)

    # Ensure xrdp and xfce4 are installed
    xrdp_packages = "xrdp dbus-x11 xfce4"
    headless_task("xrdp_install", "running")
    all_installed = True
    for pkg in xrdp_packages.split():
        rc, out = run_cmd(f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii' && echo yes || echo no")
        if out.strip() != "yes":
            all_installed = False
            break
    if all_installed:
        headless_task("xrdp_install", "done")
        headless_log("xrdp packages already installed.")
    else:
        headless_log(f"Installing {xrdp_packages} (this may take a while)...")
        rc, out = run_cmd(f"sudo apt install -y {xrdp_packages} 2>&1")
        headless_task("xrdp_install", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to install xrdp packages: {out}")
            exit_code = 1

    # Configure port (only change the first uncommented port= line)
    headless_task("xrdp_port", "running")
    headless_log(f"Setting xrdp port to {port}...")
    rc, out = run_cmd(
        f"grep -m1 '^port=' /etc/xrdp/xrdp.ini 2>/dev/null"
    )
    if out.strip() == f"port={port}":
        headless_task("xrdp_port", "done")
        headless_log(f"xrdp port already {port}.")
    else:
        rc, out = run_cmd(f"sudo sed -i '0,/^port=.*/s//port={port}/' /etc/xrdp/xrdp.ini 2>&1")
        headless_task("xrdp_port", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to set xrdp port: {out}")
            exit_code = 1

    # Configure XFCE4 session for xrdp
    headless_task("xrdp_session", "running")
    headless_log("Configuring XFCE4 session for xrdp...")
    rc, out = run_cmd(
        "grep -q 'unset DBUS_SESSION_BUS_ADDRESS' /etc/xrdp/startwm.sh 2>/dev/null"
        " && grep -q 'XDG_CURRENT_DESKTOP=XFCE' /etc/xrdp/startwm.sh 2>/dev/null"
        " && grep -q 'xfce4-session' /etc/xrdp/startwm.sh 2>/dev/null"
        " && echo yes || echo no"
    )
    if out.strip() == "yes":
        headless_task("xrdp_session", "done")
        headless_log("XFCE4 session already configured.")
    else:
        startwm = (
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
        rc, out = run_cmd(startwm)
        if rc == 0:
            run_cmd("sudo chmod +x /etc/xrdp/startwm.sh")
        headless_task("xrdp_session", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to configure XFCE4 session: {out}")
            exit_code = 1

    # Allow colord D-Bus calls without interactive polkit auth.
    # Without this the desktop crashes when any app triggers colord.
    # Ubuntu 24.04 uses polkit 124+ (JavaScript rules, not .pkla).
    headless_task("xrdp_colord", "running")
    rules_file = "/etc/polkit-1/rules.d/45-allow-colord.rules"
    rc, out = run_cmd(f"test -f {rules_file} && echo yes || echo no")
    if out.strip() == "yes":
        headless_task("xrdp_colord", "done")
        headless_log("colord polkit rule already present.")
    else:
        headless_log("Creating colord polkit rule...")
        colord_rule = (
            f"sudo tee {rules_file} > /dev/null << 'RULES'\n"
            "polkit.addRule(function(action, subject) {\n"
            '    if (action.id.indexOf("org.freedesktop.color-manager.") == 0) {\n'
            "        return polkit.Result.YES;\n"
            "    }\n"
            "});\n"
            "RULES"
        )
        rc, out = run_cmd(colord_rule)
        headless_task("xrdp_colord", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to create colord polkit rule: {out}")
            exit_code = 1

    # Fix SSL key permissions (xrdp needs to read the TLS key)
    headless_task("xrdp_ssl", "running")
    rc, out = run_cmd("id -nG xrdp 2>/dev/null")
    if "ssl-cert" in out.split():
        headless_task("xrdp_ssl", "done")
        headless_log("xrdp already in ssl-cert group.")
    else:
        headless_log("Adding xrdp to ssl-cert group...")
        rc, out = run_cmd("sudo adduser xrdp ssl-cert 2>&1")
        headless_task("xrdp_ssl", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to fix SSL permissions: {out}")
            exit_code = 1

    # Write full systemd unit replacement files for xrdp.
    # Drop-in overrides (.service.d/override.conf) DO NOT WORK for clearing
    # BindsTo= on systemd 255 -- the reset is ignored and the vendor value
    # is kept, causing sesman to be yanked down whenever the xrdp socket
    # closes.  Full replacement files completely supersede the vendor units.
    headless_task("xrdp_systemd", "running")
    headless_log("Writing systemd unit replacements for xrdp...")
    rc, out = run_cmd(
        "grep -q 'Type=exec' /etc/systemd/system/xrdp.service 2>/dev/null"
        " && grep -q 'Type=exec' /etc/systemd/system/xrdp-sesman.service 2>/dev/null"
        " && grep -q 'Restart=on-failure' /etc/systemd/system/xrdp.service 2>/dev/null"
        " && grep -q 'Restart=on-failure' /etc/systemd/system/xrdp-sesman.service 2>/dev/null"
        " && echo yes || echo no"
    )
    if out.strip() == "yes":
        headless_task("xrdp_systemd", "done")
        headless_log("systemd unit replacements already configured.")
    else:
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
        rc1, _ = run_cmd(xrdp_unit)
        rc2, _ = run_cmd(sesman_unit)
        if rc1 == 0 and rc2 == 0:
            run_cmd("sudo systemctl daemon-reload")
            headless_task("xrdp_systemd", "done")
        else:
            headless_task("xrdp_systemd", "failed")
            headless_error("Failed to write systemd unit replacements")
            exit_code = 1

    # Prevent logind from killing user services prematurely.
    # xrdp sessions are not always visible to logind, so without this
    # the user manager (and XFCE desktop) gets killed seconds after login.
    headless_task("xrdp_logind", "running")
    rc, out = run_cmd(
        "grep -q '^UserStopDelaySec=infinity' /etc/systemd/logind.conf 2>/dev/null"
        " && echo yes || echo no"
    )
    if out.strip() == "yes":
        headless_task("xrdp_logind", "done")
        headless_log("UserStopDelaySec already set.")
    else:
        headless_log("Setting UserStopDelaySec=infinity in logind.conf...")
        rc, out = run_cmd(
            r"sudo sed -i 's/^#\?UserStopDelaySec=.*/UserStopDelaySec=infinity/' /etc/systemd/logind.conf 2>&1"
        )
        if rc == 0:
            run_cmd("sudo systemctl restart systemd-logind 2>&1")
        headless_task("xrdp_logind", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to configure logind: {out}")
            exit_code = 1

    # Enable linger so user@UID.service stays alive without logind sessions.
    headless_task("xrdp_linger", "running")
    rc, user_out = run_cmd("whoami")
    user = user_out.strip()
    rc, out = run_cmd(f"loginctl show-user {user} 2>/dev/null | grep Linger=yes")
    if rc == 0 and "Linger=yes" in out:
        headless_task("xrdp_linger", "done")
        headless_log(f"Linger already enabled for {user}.")
    else:
        headless_log(f"Enabling linger for {user}...")
        rc, out = run_cmd(f"loginctl enable-linger {user} 2>&1")
        headless_task("xrdp_linger", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to enable linger: {out}")
            exit_code = 1

    # Mask GDM to prevent it from interfering with xrdp sessions.
    # GDM cycles greeter sessions on display :0 (no hardware in WSL2),
    # eventually triggering logind to issue a system power-off.
    headless_task("xrdp_gdm", "running")
    rc, out = run_cmd("systemctl is-enabled gdm 2>/dev/null")
    gdm_status = out.strip()
    if gdm_status == "masked":
        headless_task("xrdp_gdm", "done")
        headless_log("GDM already masked.")
    elif gdm_status in ("not-found", "") or "No such file" in out:
        headless_task("xrdp_gdm", "done")
        headless_log("GDM not installed.")
    else:
        headless_log("Masking GDM...")
        rc, out = run_cmd("sudo systemctl mask gdm 2>&1")
        if rc == 0:
            run_cmd("sudo systemctl stop gdm 2>/dev/null")
        headless_task("xrdp_gdm", "done" if rc == 0 else "failed")
        if rc != 0:
            headless_error(f"Failed to mask GDM: {out}")
            exit_code = 1

    # Enable and start xrdp service
    headless_task("xrdp_service", "running")
    headless_log("Enabling xrdp service...")
    rc, out = run_cmd("sudo systemctl enable --now xrdp 2>&1")
    headless_task("xrdp_service", "done" if rc == 0 else "failed")
    if rc != 0:
        headless_error(f"Failed to enable xrdp: {out}")
        exit_code = 1

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="WSL Ubuntu Setup TUI (Linux)")
    parser.add_argument("--headless", action="store_true", help="Run without TUI (structured output)")
    parser.add_argument("--step", choices=["enable-systemd", "install-packages", "configure-xrdp"],
                        help="Step to run (headless mode)")
    args = parser.parse_args()

    log = setup_logging()

    config_data = find_config()

    if args.headless:
        log.info("Headless mode, step=%s", args.step)
        try:
            if args.step == "enable-systemd":
                sys.exit(headless_enable_systemd(config_data))
            elif args.step == "install-packages":
                sys.exit(headless_install_packages(config_data))
            elif args.step == "configure-xrdp":
                sys.exit(headless_configure_xrdp(config_data))
            else:
                print("ERROR:--step required with --headless", flush=True)
                sys.exit(1)
        except SystemExit:
            sys.stdout.flush()
            raise
        except Exception:
            import traceback
            tb = traceback.format_exc()
            headless_error(tb)
            log.error("Unhandled exception in headless mode:\n%s", tb)
            sys.exit(1)
    else:
        # Interactive TUI mode
        from ..shared.config import SetupConfig
        from .app import LinuxSetupApp

        log.info("Linux interactive TUI starting")
        config = SetupConfig.from_dict(config_data)
        app = LinuxSetupApp(config)
        app.run()
        log.info("Linux TUI exited")


if __name__ == "__main__":
    main()
