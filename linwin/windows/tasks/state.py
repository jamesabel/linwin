"""Setup state persistence for reboot continuity."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ...shared.setup_logging import get_app_data_dir
from .setup_tasks import RESUME_AFTER_REBOOT


def _state_dir() -> Path:
    return get_app_data_dir()


def _state_file() -> Path:
    return _state_dir() / "setup_state.json"


@dataclass
class SetupState:
    resume_from_task: str = ""
    config_path: str = ""
    timestamp: str = ""


def save_state(state: SetupState) -> None:
    state.timestamp = datetime.now().isoformat()
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _state_file().write_text(json.dumps(asdict(state), indent=2))


def load_state() -> SetupState | None:
    sf = _state_file()
    if sf.exists():
        try:
            data = json.loads(sf.read_text())
            # Migrate old phase-based state format
            if "phase1_complete" in data and data.get("needs_reboot"):
                return SetupState(
                    resume_from_task=RESUME_AFTER_REBOOT,
                    config_path=data.get("config_path", ""),
                    timestamp=data.get("timestamp", ""),
                )
            return SetupState(**{k: v for k, v in data.items() if k in SetupState.__dataclass_fields__})
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def clear_state() -> None:
    sf = _state_file()
    if sf.exists():
        sf.unlink()


# ── Launcher selection persistence ───────────────────────────────────


def _launcher_prefs_file() -> Path:
    return _state_dir() / "launcher_prefs.json"


def save_launcher_selection(index: int) -> None:
    """Persist the last highlighted launcher item index."""
    state_dir = _state_dir()
    state_dir.mkdir(parents=True, exist_ok=True)
    _launcher_prefs_file().write_text(json.dumps({"last_selected": index}))


def load_launcher_selection() -> int:
    """Load the last highlighted launcher item index (default 0)."""
    pf = _launcher_prefs_file()
    if pf.exists():
        try:
            data = json.loads(pf.read_text())
            return data.get("last_selected", 0)
        except (json.JSONDecodeError, TypeError):
            pass
    return 0
