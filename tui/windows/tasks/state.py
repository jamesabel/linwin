"""Setup state persistence for reboot continuity."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


def _state_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        local_app_data = os.path.join(os.environ.get("USERPROFILE", "."), "AppData", "Local")
    return Path(local_app_data) / "wslubuntugnome"


def _state_file() -> Path:
    return _state_dir() / "setup_state.json"


@dataclass
class SetupState:
    phase1_complete: bool = False
    needs_reboot: bool = False
    phase2_complete: bool = False
    config_path: str = ""
    timestamp: str = ""


def save_state(state: SetupState) -> None:
    state.timestamp = datetime.now().isoformat()
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _state_file().write_text(json.dumps(asdict(state), indent=2))


def load_state() -> Optional[SetupState]:
    sf = _state_file()
    if sf.exists():
        try:
            data = json.loads(sf.read_text())
            return SetupState(**data)
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def clear_state() -> None:
    sf = _state_file()
    if sf.exists():
        sf.unlink()
