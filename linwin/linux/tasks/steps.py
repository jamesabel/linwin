"""Single source of truth for the Linux setup step sequences.

Both front-ends consume this module — the interactive TUI screen
(``linux/screens/setup.py``) and the headless runner
(``linux/__main__.py``) — so adding, removing, or renaming a step (or
its task id) happens in exactly one place and both sides stay in sync.

Each :class:`SetupStep` carries a task id, display label, and a
coroutine factory returning :class:`TaskResult`; :func:`run_steps`
executes a sequence and reports through a :class:`StepReporter`
(TUI widgets or the headless TASK/LOG/ERROR protocol).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from ...shared.config import SetupConfig, SnapPackage
from ...shared.headless_protocol import emit_error, emit_log, emit_task
from ...shared.subprocess_runner import LineCallback
from ...shared.task_result import TaskResult
from . import apt, desktop, snaps, systemd, wslg, xrdp

StepCoro = Callable[[LineCallback | None], Awaitable[TaskResult]]


@dataclass
class SetupStep:
    """One unit of Linux setup work.

    Attributes:
        task_id: Stable id used by both TUI task lists and the headless
            TASK:<id>:<status> protocol.
        label: Human-readable name shown in the TUI / logs.
        run: Coroutine factory taking the optional line callback.
        requires_snapd: Skip (as failed) when the setup_snapd step failed.
    """

    task_id: str
    label: str
    run: StepCoro
    requires_snapd: bool = False


SNAPD_STEP_ID = "setup_snapd"


async def verify_wslg_step(on_line: LineCallback | None = None) -> TaskResult:
    """Verify WSLg as a TaskResult-returning step."""
    r = await wslg.verify_wslg(on_line)
    ok = r.display_set and r.wslg_dir_exists
    parts = [
        f"DISPLAY={r.display_value or '(not set)'}",
        f"/mnt/wslg {'exists' if r.wslg_dir_exists else 'not found'}",
    ]
    if r.xeyes_works is True:
        parts.append("xeyes launched successfully — WSLg working")
    elif r.xeyes_works is False:
        parts.append("xeyes failed to launch")
    return TaskResult(ok=ok, message="; ".join(parts))


def build_package_steps(config: SetupConfig, include_systemd: bool = True) -> list[SetupStep]:
    """Build the package-setup step sequence from config.

    ``include_systemd=False`` is used by the headless install-packages
    step, where enable-systemd runs as its own separately-invoked step.
    """
    steps: list[SetupStep] = []
    if include_systemd and config.enableSystemd:
        steps.append(SetupStep("enable_systemd", "Enable systemd", systemd.enable_systemd))
    steps.append(SetupStep("apt_update", "apt update", apt.apt_update))
    steps.append(SetupStep("apt_upgrade", "apt upgrade", apt.apt_upgrade))
    for pkg in config.aptPackages:
        steps.append(SetupStep(
            f"apt_{pkg}", f"Install {pkg}",
            lambda on_line=None, p=pkg: apt.install_apt_package(p, on_line),
        ))
    steps.append(SetupStep(SNAPD_STEP_ID, "Setup snapd", snaps.setup_snapd))
    # Optional apps: snap and apt are auto-installed; custom are skipped.
    for app in config.optionalApps:
        if app.install_method == "snap":
            steps.append(SetupStep(
                f"snap_{app.id}", f"Install {app.display_name} (snap)",
                lambda on_line=None, a=app: snaps.install_snap(SnapPackage(a.id, a.classic), on_line),
                requires_snapd=True,
            ))
        elif app.install_method == "apt":
            steps.append(SetupStep(
                f"apt_opt_{app.id}", f"Install {app.display_name} (apt)",
                lambda on_line=None, a=app: apt.install_apt_package(a.id, on_line),
            ))
    steps.append(SetupStep(
        "desktop_icons", "Create desktop shortcuts",
        lambda on_line=None, a=tuple(config.optionalApps):
            desktop.create_desktop_icons(list(a), on_line),
    ))
    steps.append(SetupStep("verify_wslg", "Verify WSLg", verify_wslg_step))
    return steps


def build_xrdp_steps(config: SetupConfig) -> list[SetupStep]:
    """Build the xrdp configuration step sequence."""
    port = config.xrdpPort
    return [
        SetupStep("xrdp_install", "Install xrdp + XFCE4", xrdp.install_xrdp),
        SetupStep("xrdp_port", f"Configure xrdp port {port}",
                  lambda on_line=None, p=port: xrdp.configure_xrdp_port(p, on_line)),
        SetupStep("xrdp_session", "Configure XFCE4 session", xrdp.configure_xrdp_session),
        SetupStep("xrdp_browser", "Configure default web browser", xrdp.configure_default_browser),
        SetupStep("xrdp_service", "Enable xrdp service", xrdp.enable_xrdp_service),
    ]


def build_systemd_steps(config: SetupConfig) -> list[SetupStep]:
    """Build the enable-systemd step sequence (single step)."""
    return [SetupStep("enable_systemd", "Enable systemd", systemd.enable_systemd)]


# ── Reporting ────────────────────────────────────────────────────────


class StepReporter(Protocol):
    """How run_steps reports progress (TUI widgets or headless protocol).

    ``detail`` explains *why* a status was set (e.g. the skip reason).
    """

    def set_status(self, task_id: str, status: str, detail: str = "") -> None: ...
    def command(self, msg: str) -> None: ...
    def info(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


class HeadlessReporter:
    """Reports through the TASK/LOG/ERROR line protocol."""

    def set_status(self, task_id: str, status: str, detail: str = "") -> None:
        emit_task(task_id, status)
        if detail:
            emit_log(detail)

    def command(self, msg: str) -> None:
        emit_log(msg)

    def info(self, msg: str) -> None:
        emit_log(msg)

    def error(self, msg: str) -> None:
        emit_error(msg)


async def run_steps(
    steps: list[SetupStep],
    reporter: StepReporter,
    on_line: LineCallback | None = None,
) -> bool:
    """Run setup steps in order, reporting running/done/skipped/failed.

    Steps marked ``requires_snapd`` are failed without running when the
    setup_snapd step failed. Returns True when no step failed.
    """
    all_ok = True
    snapd_ok = True
    for step in steps:
        if step.requires_snapd and not snapd_ok:
            reporter.set_status(step.task_id, "failed", "snapd unavailable")
            reporter.error(f"{step.label} skipped: snapd unavailable")
            all_ok = False
            continue
        reporter.set_status(step.task_id, "running")
        reporter.command(f"{step.label}...")
        result = await step.run(on_line)
        if result.skipped:
            reporter.set_status(step.task_id, "skipped", result.message)
        elif result.ok:
            reporter.set_status(step.task_id, "done")
            if result.needs_restart:
                reporter.info(f"{result.message} (WSL restart needed to take effect)")
            elif result.message:
                reporter.info(result.message)
        else:
            reporter.set_status(step.task_id, "failed")
            reporter.error(result.message)
            all_ok = False
            if step.task_id == SNAPD_STEP_ID:
                snapd_ok = False
    return all_ok
