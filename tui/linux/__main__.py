#!/usr/bin/env python3
"""Linux-side TUI entry point for WSL Ubuntu setup.

Usage:
    python3 -m tui.linux                    # Interactive TUI
    python3 -m tui.linux --headless --phase 1  # Headless: enable systemd
    python3 -m tui.linux --headless --phase 2  # Headless: install packages
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


def main() -> None:
    parser = argparse.ArgumentParser(description="WSL Ubuntu Setup TUI (Linux)")
    parser.add_argument("--headless", action="store_true", help="Run without TUI (structured output)")
    parser.add_argument("--phase", type=int, choices=[1, 2], help="Phase to run (headless mode)")
    args = parser.parse_args()

    log = setup_logging()

    config_data = find_config()

    if args.headless:
        log.info("Headless mode, phase %s", args.phase)
        try:
            if args.phase == 1:
                sys.exit(headless_phase1(config_data))
            elif args.phase == 2:
                sys.exit(headless_phase2(config_data))
            else:
                print("ERROR:--phase required with --headless", flush=True)
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
