#!/usr/bin/env python3
"""Windows-side TUI entry point for WSL2 + Ubuntu + WSLg setup."""

import sys


def main() -> None:
    from ..shared.config import load_config
    from .app import WindowsSetupApp, check_admin, relaunch_as_admin

    if not check_admin():
        print("This setup requires Administrator privileges.")
        print("Requesting elevation via UAC...")
        try:
            relaunch_as_admin()
        except Exception as e:
            print(f"Failed to elevate: {e}")
            print("Please right-click and 'Run as administrator'.")
            sys.exit(1)
        sys.exit(0)

    try:
        config = load_config()
    except FileNotFoundError:
        print("ERROR: config.json not found. Please run from the project directory.")
        sys.exit(1)

    app = WindowsSetupApp(config)
    app.run()


if __name__ == "__main__":
    main()
