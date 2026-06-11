"""WSL installation, distro management, and relocation tasks."""

from __future__ import annotations

import os
import tempfile

from ...shared.config import SetupConfig
from ...shared.subprocess_runner import LineCallback, SubprocessResult, run_wsl, run_wsl_exec
from ...shared.task_result import TaskResult


async def update_wsl(on_line: LineCallback | None = None) -> TaskResult:
    """Run wsl --update."""
    result = await run_wsl_exec(["--update"], on_line=on_line, timeout=120)
    if result.success:
        return TaskResult(True, "WSL updated")
    return TaskResult(False, "WSL update failed")


async def set_wsl_default_version(on_line: LineCallback | None = None) -> TaskResult:
    """Set WSL default version to 2."""
    result = await run_wsl_exec(["--set-default-version", "2"], on_line=on_line)
    if result.success:
        return TaskResult(True, "Default version set to 2")
    return TaskResult(False, "Failed to set default version")


async def get_registered_distros(on_line: LineCallback | None = None) -> list[str]:
    """Get list of registered WSL distros."""
    result = await run_wsl_exec(["-l", "-q"], on_line=on_line)
    if not result.success:
        return []
    distros = []
    for line in result.stdout_lines:
        cleaned = line.replace("\x00", "").strip()
        if cleaned:
            distros.append(cleaned)
    return distros


async def is_distro_registered(config: SetupConfig, on_line: LineCallback | None = None) -> bool:
    """Check if the target distro is already registered."""
    distros = await get_registered_distros(on_line)
    return config.distroImportName in distros or config.distroName in distros


async def is_distro_on_target_drive(config: SetupConfig, on_line: LineCallback | None = None) -> bool:
    """Check if the distro VHD is already on the target drive."""
    vhd_path = os.path.join(config.wslInstallPath, "ext4.vhdx")
    return os.path.exists(vhd_path)


async def install_distro(config: SetupConfig, on_line: LineCallback | None = None) -> TaskResult:
    """Install the Ubuntu distro via wsl --install. Returns after the install command completes."""
    if await is_distro_registered(config, on_line):
        return TaskResult(True, "Distro already registered", skipped=True)

    # --no-launch: without it WSL starts the distro's interactive OOBE
    # ("Enter new UNIX username:"), which can never be answered from the
    # TUI and would block until the timeout. The user account is created
    # explicitly later (see create_default_user).
    result = await run_wsl_exec(
        ["--install", "-d", config.distroName, "--no-launch"],
        on_line=on_line,
        timeout=600,
    )
    if result.success:
        return TaskResult(True, f"{config.distroName} installed")
    return TaskResult(False, f"Failed to install {config.distroName}")


async def export_distro(config: SetupConfig, on_line: LineCallback | None = None) -> tuple[TaskResult, str]:
    """Export the distro to a temp tar file. Returns (result, tar_path)."""
    if await is_distro_on_target_drive(config, on_line):
        return TaskResult(True, "Distro already on target drive", skipped=True), ""

    # Find the registered name
    distros = await get_registered_distros(on_line)
    current_name = None
    for name in [config.distroImportName, config.distroName]:
        if name in distros:
            current_name = name
            break
    if not current_name:
        return TaskResult(False, "Distro not found in registry"), ""

    export_path = os.path.join(tempfile.gettempdir(), "wsl_ubuntu_export.tar")
    result = await run_wsl_exec(["--export", current_name, export_path], on_line=on_line, timeout=600)
    if result.success:
        return TaskResult(True, f"Exported to {export_path}"), export_path
    return TaskResult(False, "Export failed"), ""


async def import_distro(config: SetupConfig, tar_path: str, on_line: LineCallback | None = None) -> TaskResult:
    """Unregister old distro, import to target path."""
    if await is_distro_on_target_drive(config, on_line):
        return TaskResult(True, "Distro already on target drive", skipped=True)

    # Unregister old
    distros = await get_registered_distros(on_line)
    for name in [config.distroImportName, config.distroName]:
        if name in distros:
            await run_wsl_exec(["--unregister", name], on_line=on_line)

    # Create directory
    os.makedirs(config.wslInstallPath, exist_ok=True)

    # Import
    result = await run_wsl_exec(
        ["--import", config.distroImportName, config.wslInstallPath, tar_path, "--version", "2"],
        on_line=on_line,
        timeout=600,
    )

    # Clean up tar
    try:
        os.remove(tar_path)
    except OSError:
        pass

    if result.success:
        return TaskResult(True, f"Imported to {config.wslInstallPath}")
    return TaskResult(False, "Import failed")


async def detect_default_user(config: SetupConfig, on_line: LineCallback | None = None) -> str | None:
    """Detect the non-root user from /home/ inside the distro."""
    result = await run_wsl(config.distroImportName, "ls /home/ 2>/dev/null", on_line=on_line, timeout=60)
    if result.success and result.stdout_lines:
        users = [u.strip() for u in result.stdout_lines if u.strip() and u.strip() != "root"]
        return users[0] if users else None
    return None


async def get_configured_default_user(config: SetupConfig, on_line: LineCallback | None = None) -> str | None:
    """Read the default user already set in /etc/wsl.conf, if any.

    When a default is configured, that user — not the first /home entry —
    is who the headless setup steps run as, so passwordless sudo must be
    granted to them.
    """
    result = await run_wsl(
        config.distroImportName,
        "grep -m1 '^default=' /etc/wsl.conf 2>/dev/null | cut -d= -f2",
        on_line=on_line,
        timeout=60,
    )
    if result.success:
        user = result.output.strip()
        return user or None
    return None


async def create_default_user(
    config: SetupConfig, username: str = "ubuntu", on_line: LineCallback | None = None
) -> TaskResult:
    """Create the default non-root user when none exists.

    With ``--no-launch`` the OOBE never runs, so user creation is our
    job. Runs while the distro's default user is still root
    (post-import), so no sudo password is needed.
    """
    result = await run_wsl(
        config.distroImportName,
        f"sudo useradd -m -s /bin/bash -G sudo,adm,dialout,cdrom,floppy,audio,dip,video,plugdev {username}",
        on_line=on_line,
        timeout=60,
    )
    if result.success:
        return TaskResult(True, f"Created user {username}")
    return TaskResult(False, f"Failed to create user {username}")


async def ensure_passwordless_sudo(
    config: SetupConfig, username: str, on_line: LineCallback | None = None
) -> TaskResult:
    """Install a NOPASSWD sudoers drop-in for the default user.

    The headless Linux setup steps run sudo with no usable tty; without
    NOPASSWD, sudo blocks on an invisible password prompt (or fails with
    "a terminal is required"). Must run while sudo is still passwordless
    — i.e. while the distro default user is root, before set_default_user.
    """
    drop_in = f"/etc/sudoers.d/linwin-{username}"
    check = await run_wsl(
        config.distroImportName,
        f"test -f {drop_in} && echo yes || echo no",
        on_line=on_line,
        timeout=60,
    )
    if check.output.strip() == "yes":
        return TaskResult(True, "Passwordless sudo already configured", skipped=True)

    cmd = (
        f"echo '{username} ALL=(ALL) NOPASSWD:ALL' | sudo tee {drop_in} > /dev/null && "
        f"sudo chmod 0440 {drop_in} && sudo visudo -cf {drop_in}"
    )
    result = await run_wsl(config.distroImportName, cmd, on_line=on_line, timeout=60)
    if result.success:
        return TaskResult(True, f"Passwordless sudo configured for {username}")
    return TaskResult(False, f"Failed to configure passwordless sudo for {username}")


async def set_default_user(config: SetupConfig, username: str, on_line: LineCallback | None = None) -> TaskResult:
    """Set the default user in /etc/wsl.conf.

    Replaces a wrong existing ``default=`` (e.g. a leftover
    ``default=root``) instead of skipping whenever a ``[user]`` section
    happens to exist. Takes effect on the next WSL restart.
    """
    current = await get_configured_default_user(config, on_line)
    if current == username:
        return TaskResult(True, "Default user already configured", skipped=True)

    if current:
        # A different default exists — replace it in place.
        cmd = f"sudo sed -i 's/^default=.*/default={username}/' /etc/wsl.conf"
    else:
        check = await run_wsl(
            config.distroImportName,
            "grep -q '\\[user\\]' /etc/wsl.conf 2>/dev/null && echo yes || echo no",
            on_line=on_line,
            timeout=60,
        )
        if check.output.strip() == "yes":
            # Section exists without a default= line — add one under it.
            cmd = f"sudo sed -i '/\\[user\\]/a default={username}' /etc/wsl.conf"
        else:
            cmd = (
                f"echo '' | sudo tee -a /etc/wsl.conf > /dev/null && "
                f"echo '[user]' | sudo tee -a /etc/wsl.conf > /dev/null && "
                f"echo 'default={username}' | sudo tee -a /etc/wsl.conf > /dev/null"
            )
    result = await run_wsl(config.distroImportName, cmd, on_line=on_line, timeout=60)
    if result.success:
        return TaskResult(True, f"Default user set to {username}")
    return TaskResult(False, "Failed to set default user")


async def shutdown_wsl(on_line: LineCallback | None = None) -> TaskResult:
    """Shut down all WSL instances."""
    result = await run_wsl_exec(["--shutdown"], on_line=on_line)
    return TaskResult(True, "WSL shut down")


async def wait_for_wsl_ready(
    config: SetupConfig,
    on_line: LineCallback | None = None,
    max_attempts: int = 10,
    require_systemd: bool = True,
) -> bool:
    """Wait until the WSL distro is responsive after a restart.

    Probes with a simple 'echo ready' command every 2 seconds, then —
    when ``require_systemd`` is True — verifies systemd services
    (including xrdp if installed) have settled before returning.

    Pass ``require_systemd=False`` before the enable-systemd setup step
    has run: systemd is not PID 1 yet, so the phase-2 probe could never
    succeed and would burn all attempts.

    Returns True when WSL responds, False if all attempts exhausted.
    """
    import asyncio

    # Phase 1: wait for basic shell responsiveness
    for attempt in range(max_attempts):
        result = await run_wsl(config.distroImportName, "echo ready", on_line=on_line, timeout=30)
        if result.success and "ready" in result.output:
            break
        await asyncio.sleep(2)
    else:
        return False

    if not require_systemd:
        return True

    # Phase 2: wait for systemd to finish booting and xrdp to stabilise.
    # Each value is tagged with a marker so a sub-command with empty
    # output can't shift the others into the wrong field.
    for attempt in range(max_attempts):
        result = await run_wsl(
            config.distroImportName,
            'echo "STATE:$(systemctl is-system-running 2>/dev/null)"; '
            'echo "XRDP:$(systemctl is-active xrdp 2>/dev/null)"; '
            'echo "SESMAN:$(systemctl is-active xrdp-sesman 2>/dev/null)"',
            on_line=on_line,
            timeout=30,
        )
        values = {"STATE": "", "XRDP": "", "SESMAN": ""}
        for line in result.stdout_lines:
            key, sep, value = line.strip().partition(":")
            if sep and key in values:
                values[key] = value.strip()
        system_state = values["STATE"]
        xrdp_active = values["XRDP"]
        sesman_active = values["SESMAN"]

        # System must be running/degraded (not "starting")
        if system_state in ("running", "degraded"):
            # If xrdp is not installed, we're done
            if xrdp_active in ("inactive", "not-found", ""):
                return True
            # If xrdp is installed, both services must be active
            if xrdp_active == "active" and sesman_active == "active":
                return True
        await asyncio.sleep(2)
    return False
