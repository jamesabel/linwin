"""Launch WSL GUI apps and terminals from Windows."""

from __future__ import annotations

import subprocess
import sys


# Mapping of button IDs to (command, display_name).
# Screens use this to resolve btn-launch-* clicks.
WSL_APP_BUTTONS: dict[str, tuple[str, str]] = {
    "btn-launch-files": ("nautilus", "File Manager"),
    "btn-launch-pycharm": ("pycharm-community", "PyCharm"),
}


def launch_wsl_app(distro: str, *args: str) -> None:
    """Launch a GUI app inside WSL (non-blocking, fire-and-forget).

    Raises on failure so the caller can display an error notification.
    """
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        ["wsl.exe", "-d", distro, "--"] + list(args),
        **kwargs,
    )


def launch_windows_terminal(profile: str = "Ubuntu") -> None:
    """Open a Windows Terminal tab with the given profile."""
    subprocess.Popen(["wt.exe", "-p", profile])
