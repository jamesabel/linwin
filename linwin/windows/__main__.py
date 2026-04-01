#!/usr/bin/env python3
"""Windows-side TUI entry point for WSL2 + Ubuntu + WSLg setup.

The app starts without requiring admin privileges.  Admin elevation is
requested on-demand only for the specific operations that need it
(enabling Windows features via DISM, setting up port proxy via netsh).
"""

import sys


def main() -> None:
    from ..shared.config import load_config, get_config_db_path
    from ..shared.setup_logging import get_log_dir, setup_logging
    from .app import WindowsSetupApp, check_admin

    log = setup_logging()

    if check_admin():
        log.info("Running as Administrator")
    else:
        log.info("Running as standard user (admin will be requested when needed)")

    try:
        config = load_config()
    except Exception as e:
        log.error("Failed to load config: %s", e)
        print(f"ERROR: Failed to load config: {e}")
        sys.exit(1)

    log.info("Config loaded: distro=%s drive=%s: path=%s",
             config.distroName, config.wslDriveLetter, config.wslInstallPath)
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
