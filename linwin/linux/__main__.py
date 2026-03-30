#!/usr/bin/env python3
"""Linux-side TUI entry point for WSL Ubuntu setup.

Usage:
    python3 -m linwin.linux                                       # Interactive TUI
    python3 -m linwin.linux --headless --step enable-systemd      # Headless: enable systemd
    python3 -m linwin.linux --headless --step install-packages    # Headless: install packages
"""

import argparse
import asyncio
import json
import logging
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


def _run_task(task_id: str, coro, success_msg: str = "") -> bool:
    """Run an async task with structured headless output. Returns True on success."""
    headless_task(task_id, "running")
    result = asyncio.run(coro)
    if hasattr(result, "ok"):
        if getattr(result, "skipped", False):
            headless_task(task_id, "done")
            headless_log(result.message)
        elif result.ok:
            headless_task(task_id, "done")
            headless_log(success_msg or result.message)
        else:
            headless_task(task_id, "failed")
            headless_error(result.message)
            return False
    else:
        # Boolean or other non-TaskResult return value
        headless_task(task_id, "done")
    return True


def headless_enable_systemd(config: dict) -> int:
    """Enable systemd in wsl.conf. Delegates to the async implementation in tasks.systemd."""
    from .tasks.systemd import enable_systemd

    if not _run_task("enable_systemd", enable_systemd()):
        return 1
    return 0


def headless_install_packages(config: dict) -> int:
    """Install apt packages, snaps, verify WSLg. Delegates to async task modules."""
    from .tasks import apt, snaps, wslg
    from ..shared.config import SnapPackage

    exit_code = 0

    # apt update & upgrade
    if not _run_task("apt_update", apt.apt_update()):
        exit_code = 1
    if not _run_task("apt_upgrade", apt.apt_upgrade()):
        exit_code = 1

    # apt packages
    for pkg in config.get("aptPackages", []):
        if not _run_task(f"apt_{pkg}", apt.install_apt_package(pkg)):
            exit_code = 1

    # Setup snapd
    headless_task("setup_snapd", "running")
    systemd_ok = asyncio.run(snaps.check_systemd_running())
    if not systemd_ok:
        headless_task("setup_snapd", "failed")
        headless_error("systemd not running. Snaps require systemd + WSL restart.")
        exit_code = 1
    else:
        result = asyncio.run(snaps.ensure_snapd())
        if result.ok:
            headless_task("setup_snapd", "done")
            headless_log(result.message)
        else:
            headless_task("setup_snapd", "failed")
            headless_error(result.message)
            exit_code = 1

        # Install snaps
        for snap_info in config.get("snaps", []):
            snap = SnapPackage(
                name=snap_info["name"],
                classic=snap_info.get("classic", True),
            )
            if not _run_task(f"snap_{snap.name}", snaps.install_snap(snap)):
                exit_code = 1

    # Verify WSLg
    headless_task("verify_wslg", "running")
    wslg_result = asyncio.run(wslg.verify_wslg())
    headless_log(f"DISPLAY={wslg_result.display_value or '(not set)'}")
    headless_log(f"/mnt/wslg: {'exists' if wslg_result.wslg_dir_exists else 'not found'}")
    wslg_ok = wslg_result.display_set and wslg_result.wslg_dir_exists
    headless_task("verify_wslg", "done" if wslg_ok else "failed")

    return exit_code


def headless_configure_xrdp(config: dict) -> int:
    """Install xrdp + xfce4, configure port/session, enable service.

    Delegates to async task functions in tasks.xrdp. The enable_xrdp_service
    call internally handles SSL permissions, systemd overrides, colord polkit,
    logind delay, user linger, and GDM masking.
    """
    from .tasks import xrdp

    exit_code = 0
    port = config.get("xrdpPort", 3390)

    if not _run_task("xrdp_install", xrdp.install_xrdp()):
        exit_code = 1
    if not _run_task("xrdp_port", xrdp.configure_xrdp_port(port)):
        exit_code = 1
    if not _run_task("xrdp_session", xrdp.configure_xrdp_session()):
        exit_code = 1
    if not _run_task("xrdp_service", xrdp.enable_xrdp_service()):
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
