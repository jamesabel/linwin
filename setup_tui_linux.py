#!/usr/bin/env python3
"""Linux-side TUI entry point for WSL Ubuntu setup.

Usage:
    python3 setup_tui_linux.py                    # Interactive TUI
    python3 setup_tui_linux.py --headless --phase 1  # Headless: enable systemd
    python3 setup_tui_linux.py --headless --phase 2  # Headless: install packages
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path


def find_config() -> dict:
    """Find and load config.json."""
    script_dir = Path(__file__).resolve().parent
    config_path = script_dir / "config.json"
    if not config_path.exists():
        print(f"ERROR:config.json not found at {config_path}", flush=True)
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


# ---------- Headless mode (no textual import) ----------

def headless_task(task_id: str, status: str) -> None:
    print(f"TASK:{task_id}:{status}", flush=True)


def headless_log(msg: str) -> None:
    print(f"LOG:{msg}", flush=True)


def headless_error(msg: str) -> None:
    print(f"ERROR:{msg}", flush=True)


def run_cmd(cmd: str) -> tuple[int, str]:
    """Run a shell command synchronously, return (exit_code, output)."""
    import subprocess
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    output = result.stdout.strip()
    if result.stderr.strip():
        output += "\n" + result.stderr.strip()
    return result.returncode, output


def headless_phase1(config: dict) -> int:
    """Enable systemd in wsl.conf."""
    headless_task("enable_systemd", "running")
    headless_log("Checking if systemd is already enabled...")

    rc, out = run_cmd("grep -q 'systemd=true' /etc/wsl.conf 2>/dev/null && echo yes || echo no")
    if out.strip() == "yes":
        headless_task("enable_systemd", "done")
        headless_log("systemd already enabled in wsl.conf.")
        return 0

    # Check if [boot] section exists
    rc, out = run_cmd("grep -q '\\[boot\\]' /etc/wsl.conf 2>/dev/null && echo yes || echo no")
    has_boot = out.strip() == "yes"

    if has_boot:
        cmd = "sudo sed -i '/\\[boot\\]/a systemd=true' /etc/wsl.conf"
    else:
        cmd = (
            "echo '' | sudo tee -a /etc/wsl.conf > /dev/null && "
            "echo '[boot]' | sudo tee -a /etc/wsl.conf > /dev/null && "
            "echo 'systemd=true' | sudo tee -a /etc/wsl.conf > /dev/null"
        )

    rc, out = run_cmd(cmd)
    if rc == 0:
        headless_task("enable_systemd", "done")
        headless_log("systemd enabled. WSL restart required.")
    else:
        headless_task("enable_systemd", "failed")
        headless_error(f"Failed to enable systemd: {out}")
        return 1
    return 0


def headless_phase2(config: dict) -> int:
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


def main() -> None:
    parser = argparse.ArgumentParser(description="WSL Ubuntu Setup TUI (Linux)")
    parser.add_argument("--headless", action="store_true", help="Run without TUI (structured output)")
    parser.add_argument("--phase", type=int, choices=[1, 2], help="Phase to run (headless mode)")
    args = parser.parse_args()

    config_data = find_config()

    if args.headless:
        if args.phase == 1:
            sys.exit(headless_phase1(config_data))
        elif args.phase == 2:
            sys.exit(headless_phase2(config_data))
        else:
            print("ERROR:--phase required with --headless", flush=True)
            sys.exit(1)
    else:
        # Interactive TUI mode
        from tui.shared.config import SetupConfig
        from tui.linux.app import LinuxSetupApp

        config = SetupConfig.from_dict(config_data)
        app = LinuxSetupApp(config)
        app.run()


if __name__ == "__main__":
    main()
