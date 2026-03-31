#!/usr/bin/env python3
"""Windows-side TUI entry point for WSL2 + Ubuntu + WSLg setup."""

import sys


def main() -> None:
    from ..shared.config import load_config
    from ..shared.setup_logging import get_log_dir, setup_logging
    from .app import WindowsSetupApp, check_admin, relaunch_as_admin

    log = setup_logging()

    if not check_admin():
        log.warning("Not running as admin, requesting elevation")
        print("This setup requires Administrator privileges.")
        print("Requesting elevation via UAC...")
        try:
            relaunch_as_admin()
        except Exception as e:
            log.error("UAC elevation failed: %s", e)
            print(f"Failed to elevate: {e}")
            print("Please right-click and 'Run as administrator'.")
            sys.exit(1)
        sys.exit(0)

    log.info("Running as Administrator")

    try:
        config = load_config()
    except Exception as e:
        log.error("Failed to load config: %s", e)
        print(f"ERROR: Failed to load config: {e}")
        sys.exit(1)

    log.info("Config loaded: distro=%s drive=%s: path=%s",
             config.distroName, config.wslDriveLetter, config.wslInstallPath)
    from ..shared.config import get_config_db_path
    log.info("Config DB: %s", get_config_db_path())

    app = WindowsSetupApp(config)
    try:
        app.run()
    except Exception:
        log.exception("App crashed with unhandled exception")
        raise
    log.info("Windows TUI exited")


if __name__ == "__main__":
    main()
