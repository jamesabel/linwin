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
import sys
from pathlib import Path

from ..shared.headless_protocol import emit_error, emit_log, emit_task
from ..shared.setup_logging import setup_logging


def find_config() -> dict:
    """Load config from the pref DB, or return defaults if unavailable.

    Inside WSL the ``pref`` package may not be installed, so fall back
    to defaults.
    """
    try:
        from ..shared.config import load_config
        return load_config().to_dict()
    except ImportError:
        # pref not installed (running inside WSL) — use defaults.
        from ..shared.config import SetupConfig
        return SetupConfig().to_dict()


def _run_task(task_id: str, coro, success_msg: str = "") -> bool:
    """Run an async task with structured headless output. Returns True on success."""
    emit_task(task_id, "running")
    result = asyncio.run(coro)
    if hasattr(result, "ok"):
        if getattr(result, "skipped", False):
            emit_task(task_id, "done")
            emit_log(result.message)
        elif result.ok:
            emit_task(task_id, "done")
            emit_log(success_msg or result.message)
        else:
            emit_task(task_id, "failed")
            emit_error(result.message)
            return False
    else:
        # Boolean or other non-TaskResult return value
        emit_task(task_id, "done")
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
    emit_task("setup_snapd", "running")
    systemd_ok = asyncio.run(snaps.check_systemd_running())
    if not systemd_ok:
        emit_task("setup_snapd", "failed")
        emit_error("systemd not running. Snaps require systemd + WSL restart.")
        exit_code = 1
    else:
        result = asyncio.run(snaps.ensure_snapd())
        if result.ok:
            emit_task("setup_snapd", "done")
            emit_log(result.message)
        else:
            emit_task("setup_snapd", "failed")
            emit_error(result.message)
            exit_code = 1

        # Install optional apps (snap and apt; custom skipped)
        for app_info in config.get("optionalApps", config.get("snaps", [])):
            method = app_info.get("install_method", "snap")
            app_id = app_info.get("id", app_info.get("name", ""))
            if method == "snap":
                snap = SnapPackage(
                    name=app_id,
                    classic=app_info.get("classic", True),
                )
                if not _run_task(f"snap_{snap.name}", snaps.install_snap(snap)):
                    exit_code = 1
            elif method == "apt":
                if not _run_task(f"apt_opt_{app_id}", apt.install_apt_package(app_id)):
                    exit_code = 1

    # Verify WSLg
    emit_task("verify_wslg", "running")
    wslg_result = asyncio.run(wslg.verify_wslg())
    emit_log(f"DISPLAY={wslg_result.display_value or '(not set)'}")
    emit_log(f"/mnt/wslg: {'exists' if wslg_result.wslg_dir_exists else 'not found'}")
    wslg_ok = wslg_result.display_set and wslg_result.wslg_dir_exists
    emit_task("verify_wslg", "done" if wslg_ok else "failed")

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
            emit_error(tb)
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
