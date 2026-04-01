"""Launch WSL GUI apps and terminals from Windows."""

from __future__ import annotations

import subprocess
import sys


def notify_launch(app, command: str, display_name: str, distro: str) -> None:
    """Launch a WSL app by command and notify the user.

    Args:
        app: The Textual App instance (for notifications).
        command: Shell command to run inside WSL (e.g. "nautilus").
        display_name: Human-readable name for the notification.
        distro: WSL distro name.
    """
    try:
        launch_wsl_app(distro, command)
        app.notify(f"Launched: {display_name}")
    except Exception as e:
        app.notify(f"Failed to launch: {e}", severity="error")


def launch_wsl_app(distro: str, *args: str) -> None:
    """Launch a GUI app inside WSL (non-blocking, fire-and-forget).

    Uses ``bash -lc`` so that snap binaries in /snap/bin are on PATH.
    Starts a keepalive so the VM stays up after the TUI exits.
    Raises on failure so the caller can display an error notification.
    """
    ensure_wsl_keepalive(distro)
    cmd = " ".join(args)
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    subprocess.Popen(
        ["wsl.exe", "-d", distro, "--", "bash", "-lc", cmd],
        **kwargs,
    )


def launch_windows_terminal(profile: str = "Ubuntu") -> None:
    """Open a Windows Terminal tab with the given profile."""
    subprocess.Popen(["wt.exe", "-p", profile])


def _get_wsl_ip(distro: str = "Ubuntu") -> str:
    """Get the WSL2 NAT IP address for the given distro.

    WSL2 runs behind NAT. Used to set up the port proxy that forwards
    127.0.0.1:<port> into the VM.
    """
    try:
        result = subprocess.run(
            ["wsl.exe", "-d", distro, "--", "hostname", "-I"],
            capture_output=True, text=True, timeout=5,
        )
        ip = result.stdout.strip().split()[0]
        if ip:
            return ip
    except Exception as exc:
        import logging
        logging.getLogger("wslsetup").debug("_get_wsl_ip failed: %s", exc)
    return ""




_keepalive_proc: subprocess.Popen | None = None


def ensure_wsl_keepalive(distro: str = "Ubuntu") -> None:
    """Keep the WSL VM alive by running a background ``sleep infinity``.

    WSL2 shuts down the VM when all wsl.exe processes exit, which kills
    xrdp and any active RDP sessions.  This starts a hidden background
    process that holds the VM open indefinitely.
    """
    global _keepalive_proc
    if _keepalive_proc is not None and _keepalive_proc.poll() is None:
        return  # already running
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    _keepalive_proc = subprocess.Popen(
        ["wsl.exe", "-d", distro, "--", "sleep", "infinity"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def launch_rdp(port: int = 3390, distro: str = "Ubuntu") -> None:
    """Open Remote Desktop Connection to the WSL xrdp server.

    Connects directly to the WSL2 VM's IP address — no admin-requiring
    port proxy needed.  Starts a keepalive so the VM doesn't shut down
    when the TUI exits.
    """
    ensure_wsl_keepalive(distro)
    wsl_ip = _get_wsl_ip(distro)
    target = f"{wsl_ip}:{port}" if wsl_ip else f"127.0.0.1:{port}"
    subprocess.Popen(["mstsc.exe", f"/v:{target}"])
