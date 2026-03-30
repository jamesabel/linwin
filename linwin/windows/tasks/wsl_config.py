"""Write .wslconfig from SetupConfig."""

from __future__ import annotations

import configparser
import io
import os
from dataclasses import dataclass

from ...shared.config import SetupConfig


@dataclass
class ConfigWriteResult:
    ok: bool
    message: str
    skipped: bool = False
    existing_content: str = ""


def get_wslconfig_path() -> str:
    return os.path.join(os.environ.get("USERPROFILE", ""), ".wslconfig")


def generate_wslconfig_content(config: SetupConfig) -> str:
    wc = config.wslconfig
    cp = configparser.ConfigParser()
    cp.optionxform = str  # preserve case
    cp["wsl2"] = {
        "memory": wc.memory,
        "processors": str(wc.processors),
        "swap": wc.swap,
        "swapFile": wc.swapFile.replace("\\", "/"),
        "guiApplications": str(wc.guiApplications).lower(),
        "defaultVhdSize": wc.defaultVhdSize,
    }
    buf = io.StringIO()
    cp.write(buf)
    return buf.getvalue()


def check_wslconfig_exists() -> tuple[bool, str]:
    """Check if .wslconfig exists. Returns (exists, content)."""
    path = get_wslconfig_path()
    if os.path.exists(path):
        with open(path, "r") as f:
            return True, f.read()
    return False, ""


def write_wslconfig(config: SetupConfig, overwrite: bool = False) -> ConfigWriteResult:
    """Write .wslconfig. If it exists and overwrite is False, return existing content for user review."""
    path = get_wslconfig_path()
    content = generate_wslconfig_content(config)

    exists, existing = check_wslconfig_exists()
    if exists and not overwrite:
        return ConfigWriteResult(
            ok=False,
            message="Existing .wslconfig found",
            existing_content=existing,
        )

    # Ensure swap directory exists
    swap_dir = os.path.dirname(config.wslconfig.swapFile)
    if swap_dir:
        os.makedirs(swap_dir, exist_ok=True)

    with open(path, "w") as f:
        f.write(content)

    return ConfigWriteResult(ok=True, message=f"Written to {path}")
