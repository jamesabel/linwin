"""Live OpenClaw installation test against the disposable test clone.

Downloads and runs the official OpenClaw installer (network, ~2-5 min),
so it is gated behind LINWIN_TEST_OPENCLAW=1 and not part of default
or CI runs:

    $env:LINWIN_TEST_OPENCLAW = "1"
    uv run python -m pytest tests/test_openclaw_live.py -v
"""

from __future__ import annotations

import base64
import json
import os

import pytest

from linwin.shared.config import APP_REGISTRY, SetupConfig
from linwin.shared.subprocess_runner import run_wsl

from .helpers import _run

pytestmark = pytest.mark.skipif(
    os.environ.get("LINWIN_TEST_OPENCLAW") != "1",
    reason="set LINWIN_TEST_OPENCLAW=1 to run the live OpenClaw install test",
)


class TestOpenClawLive:
    def test_install_via_headless_step(self, distro):
        """The install-packages step installs OpenClaw end-to-end."""
        config = SetupConfig()
        config.aptPackages = []
        config.optionalApps = [a for a in APP_REGISTRY if a.id == "openclaw"]
        b64 = base64.b64encode(json.dumps(config.to_dict()).encode()).decode()

        r = _run(run_wsl(
            distro,
            f"python3 -m linwin.linux --headless --step install-packages --config-b64 {b64}",
            cwd=os.getcwd(),
            timeout=1200,
        ))
        assert r.success, f"install-packages step failed:\n{r.output}"
        assert "TASK:app_openclaw:" in r.output

        r = _run(run_wsl(distro, "bash -lc 'openclaw --version'", timeout=60))
        assert r.success and r.output.strip(), "openclaw CLI not on the login PATH"

        r = _run(run_wsl(
            distro,
            "XDG_RUNTIME_DIR=/run/user/1000 systemctl --user is-enabled openclaw-gateway 2>/dev/null",
            timeout=60,
        ))
        assert r.output.strip() == "enabled", "openclaw-gateway user service not enabled"
