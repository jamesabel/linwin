"""OpenClaw (personal AI agent) installation.

OpenClaw runs as a systemd *user* service (openclaw-gateway.service)
inside WSL. The official installer handles Node.js itself; onboarding
(API keys, channels) is interactive and left to the user:

    openclaw onboard

The gateway dashboard is served on http://localhost:18789, reachable
from Windows via WSL localhost forwarding. linwin's systemd enablement
plus user lingering keep the gateway running with no login session;
pair with the launcher's "WSL Autostart at Logon" maintenance action
to make the agent survive Windows reboots.
"""

from __future__ import annotations

from ...shared.subprocess_runner import LineCallback, run_local
from ...shared.task_result import TaskResult

ONBOARD_HINT = "run 'openclaw onboard' in an Ubuntu terminal to finish configuration"


async def install_openclaw(on_line: LineCallback | None = None) -> TaskResult:
    """Install OpenClaw via the official installer and enable its gateway.

    Idempotent: skips when the CLI is already on the login-shell PATH.
    The installer is run non-interactively (--no-onboard) since setup
    has no tty; Node.js is handled by the installer itself.
    """
    check = await run_local(
        "bash -lc 'command -v openclaw' > /dev/null 2>&1 && echo yes || echo no",
        on_line,
        timeout=30,
    )
    if check.output.strip() == "yes":
        return TaskResult(ok=True, message="OpenClaw already installed", skipped=True)

    result = await run_local(
        "curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard",
        on_line,
        timeout=900,
    )
    if not result.success:
        return TaskResult(ok=False, message="OpenClaw installer failed")

    # Lingering keeps the gateway user service alive with no login
    # session (idempotent; normally already enabled by the xrdp step,
    # but don't depend on step ordering).
    await run_local('sudo loginctl enable-linger "$(whoami)"', on_line, timeout=30)

    service = await run_local(
        "bash -lc 'openclaw gateway install'",
        on_line,
        timeout=120,
    )
    if not service.success:
        return TaskResult(
            ok=False,
            message=f"OpenClaw installed but gateway service setup failed — {ONBOARD_HINT}",
        )
    return TaskResult(ok=True, message=f"OpenClaw installed; {ONBOARD_HINT}")
