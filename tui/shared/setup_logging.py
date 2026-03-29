"""File logging for the WSL Ubuntu setup tool.

Writes a rotating log file to:
  Windows: %LOCALAPPDATA%\\wslubuntugnome\\logs\\setup.log
  Linux:   ~/.local/share/wslubuntugnome/logs/setup.log
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_INITIALIZED = False


def get_log_dir() -> Path:
    """Return the platform-appropriate directory for log files."""
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            local_app_data = os.path.join(
                os.environ.get("USERPROFILE", "."), "AppData", "Local"
            )
        return Path(local_app_data) / "wslubuntugnome" / "logs"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        if not xdg:
            xdg = os.path.join(os.path.expanduser("~"), ".local", "share")
        return Path(xdg) / "wslubuntugnome" / "logs"


def setup_logging() -> logging.Logger:
    """Initialize file logging and return the app logger.

    Safe to call multiple times; only the first call attaches handlers.
    """
    global _LOG_INITIALIZED

    logger = logging.getLogger("wslsetup")

    if _LOG_INITIALIZED:
        return logger

    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "setup.log"

    handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    _LOG_INITIALIZED = True
    logger.info("=" * 60)
    logger.info("WSL Ubuntu Setup started  (platform=%s)", sys.platform)
    logger.info("Log file: %s", log_file)

    return logger


def get_logger() -> logging.Logger:
    """Get the app logger, initializing if needed."""
    return setup_logging()
