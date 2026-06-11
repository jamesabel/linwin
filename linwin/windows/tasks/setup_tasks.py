"""The ordered Windows setup task list and reboot-resume pointer.

Lives outside the UI layer so non-screen code (e.g. state migration in
``state.py``) can reference task ids without importing Textual screens.
"""

from __future__ import annotations

SETUP_TASKS = [
    # Feature checks / enables (may require reboot)
    ("validate_build", "Validate Windows build"),
    ("check_virt", "Check virtualization"),
    ("check_drive", "Check target drive"),
    ("check_wsl", "Check WSL feature"),
    ("enable_wsl", "Enable WSL feature"),
    ("check_vm", "Check VM Platform feature"),
    ("enable_vm", "Enable VM Platform feature"),
    # WSL install + Linux setup (post-reboot if needed)
    ("update_wsl", "Update WSL"),
    ("set_version", "Set WSL default version 2"),
    ("install_distro", "Install Ubuntu"),
    ("export_distro", "Export distro"),
    ("import_distro", "Import distro to target drive"),
    ("set_user", "Set default user"),
    ("write_config", "Write .wslconfig"),
    ("shutdown_wsl", "Shutdown WSL"),
    ("linux_systemd", "Linux setup: enable systemd"),
    ("restart_wsl", "Restart WSL"),
    ("linux_packages", "Linux setup: install packages"),
    ("linux_xrdp", "Linux setup: install and configure xrdp"),
]

# First task to run after the feature-enable reboot. If tasks before
# update_wsl are added or reordered, keep this pointing at the first
# post-reboot task.
RESUME_AFTER_REBOOT = "update_wsl"

TASK_IDS = [t[0] for t in SETUP_TASKS]
