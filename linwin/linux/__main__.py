#!/usr/bin/env python3
"""Linux-side TUI entry point for WSL Ubuntu setup.

Usage:
    python3 -m linwin.linux                                       # Interactive TUI
    python3 -m linwin.linux --headless --step enable-systemd      # Headless: enable systemd
    python3 -m linwin.linux --headless --step install-packages    # Headless: install packages

In headless mode the Windows orchestrator passes the user's SetupConfig
as base64-encoded JSON via ``--config-b64``; without it (interactive use
inside WSL) config falls back to the local pref DB or defaults.
"""

import argparse
import asyncio
import base64
import json
import sys

from ..shared.config import SetupConfig
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
        return SetupConfig().to_dict()


async def _emit_output_line(line: str, stream: str) -> None:
    """Relay live subprocess output (apt, snap, ...) as LOG lines.

    Long steps like apt upgrade run for minutes — without this the
    Windows TUI shows nothing between 'running' and 'done' and looks
    stuck.
    """
    emit_log(line)


def headless_enable_systemd(config: SetupConfig) -> int:
    """Enable systemd in wsl.conf (honors config.enableSystemd)."""
    from .tasks.steps import HeadlessReporter, build_systemd_steps, run_steps

    if not config.enableSystemd:
        emit_task("enable_systemd", "skipped")
        emit_log("enableSystemd is disabled in the configuration")
        return 0
    ok = asyncio.run(run_steps(build_systemd_steps(config), HeadlessReporter(),
                               on_line=_emit_output_line))
    return 0 if ok else 1


def headless_install_packages(config: SetupConfig) -> int:
    """Install apt packages, snaps, verify WSLg via the shared step list."""
    from .tasks.steps import HeadlessReporter, build_package_steps, run_steps

    # enable-systemd runs as its own separately-invoked headless step.
    steps = build_package_steps(config, include_systemd=False)
    ok = asyncio.run(run_steps(steps, HeadlessReporter(), on_line=_emit_output_line))
    return 0 if ok else 1


def headless_configure_xrdp(config: SetupConfig) -> int:
    """Install xrdp + xfce4, configure port/session, enable service."""
    from .tasks.steps import HeadlessReporter, build_xrdp_steps, run_steps

    ok = asyncio.run(run_steps(build_xrdp_steps(config), HeadlessReporter(),
                               on_line=_emit_output_line))
    return 0 if ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="WSL Ubuntu Setup TUI (Linux)")
    parser.add_argument("--headless", action="store_true", help="Run without TUI (structured output)")
    parser.add_argument("--step", choices=["enable-systemd", "install-packages", "configure-xrdp"],
                        help="Step to run (headless mode)")
    parser.add_argument("--config-b64", default=None,
                        help="Base64-encoded JSON SetupConfig (passed by the Windows orchestrator)")
    args = parser.parse_args()

    log = setup_logging()

    if args.config_b64:
        config_data = json.loads(base64.b64decode(args.config_b64))
    else:
        config_data = find_config()
    config = SetupConfig.from_dict(config_data)

    if args.headless:
        log.info("Headless mode, step=%s", args.step)
        try:
            if args.step == "enable-systemd":
                sys.exit(headless_enable_systemd(config))
            elif args.step == "install-packages":
                sys.exit(headless_install_packages(config))
            elif args.step == "configure-xrdp":
                sys.exit(headless_configure_xrdp(config))
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
        from .app import LinuxSetupApp

        log.info("Linux interactive TUI starting")
        app = LinuxSetupApp(config)
        app.run()
        log.info("Linux TUI exited")


if __name__ == "__main__":
    main()
