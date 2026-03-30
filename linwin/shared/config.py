"""Shared configuration loading, validation, and serialization."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


@dataclass
class WslConfig:
    memory: str = "16GB"
    processors: int = 8
    swap: str = "8GB"
    swapFile: str = "V:\\WSL\\swap.vhdx"
    guiApplications: bool = True
    defaultVhdSize: str = "200GB"


@dataclass
class SnapPackage:
    name: str
    classic: bool = True


# Snap packages offered in the config editor UI.
AVAILABLE_SNAPS: list[tuple[str, str]] = [
    ("code", "VS Code"),
    ("intellij-idea-community", "IntelliJ IDEA Community"),
    ("pycharm-community", "PyCharm Community"),
]


@dataclass
class SetupConfig:
    distroName: str = "Ubuntu-22.04"
    distroImportName: str = "Ubuntu"
    wslInstallPath: str = "V:\\WSL\\Ubuntu"
    wslDriveLetter: str = "V"
    wslconfig: WslConfig = field(default_factory=WslConfig)
    snaps: list[SnapPackage] = field(default_factory=lambda: [
        SnapPackage("code", True),
        SnapPackage("intellij-idea-community", True),
        SnapPackage("pycharm-community", True),
    ])
    aptPackages: list[str] = field(default_factory=lambda: ["nautilus", "x11-apps"])
    enableSystemd: bool = True
    xrdpPort: int = 3390

    @staticmethod
    def from_dict(data: dict) -> SetupConfig:
        wslconfig = WslConfig(**data.get("wslconfig", {}))
        snaps = [SnapPackage(**s) for s in data.get("snaps", [])]
        return SetupConfig(
            distroName=data.get("distroName", "Ubuntu-22.04"),
            distroImportName=data.get("distroImportName", "Ubuntu"),
            wslInstallPath=data.get("wslInstallPath", "V:\\WSL\\Ubuntu"),
            wslDriveLetter=data.get("wslDriveLetter", "V"),
            wslconfig=wslconfig,
            snaps=snaps,
            aptPackages=data.get("aptPackages", ["nautilus", "x11-apps"]),
            enableSystemd=data.get("enableSystemd", True),
            xrdpPort=data.get("xrdpPort", 3390),
        )

    def to_dict(self) -> dict:
        return asdict(self)


def get_config_path(script_path: str | None = None) -> Path:
    """Find config.json relative to the given script or the package root."""
    if script_path:
        p = Path(script_path).resolve().parent / "config.json"
        if p.exists():
            return p
    # Walk up from this file to find the repo root config.json
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / "config.json"
        if candidate.exists():
            return candidate
        current = current.parent
    raise FileNotFoundError("config.json not found")


def load_config(path: Path | None = None) -> SetupConfig:
    if path is None:
        path = get_config_path()
    with open(path, "r") as f:
        data = json.load(f)
    return SetupConfig.from_dict(data)


def save_config(config: SetupConfig, path: Path | None = None) -> None:
    if path is None:
        path = get_config_path()
    with open(path, "w") as f:
        json.dump(config.to_dict(), f, indent=4)
        f.write("\n")


def validate_config(config: SetupConfig) -> list[str]:
    """Return a list of validation error messages (empty = valid)."""
    errors = []
    if not config.distroName:
        errors.append("distroName is required")
    if not config.distroImportName:
        errors.append("distroImportName is required")
    if not config.wslDriveLetter or len(config.wslDriveLetter) != 1:
        errors.append("wslDriveLetter must be a single letter")
    if not config.wslInstallPath:
        errors.append("wslInstallPath is required")
    if config.wslconfig.processors < 1:
        errors.append("processors must be at least 1")
    return errors


def windows_to_wsl_path(win_path: str) -> str:
    """Convert C:\\foo\\bar to /mnt/c/foo/bar."""
    path = win_path.replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        rest = path[2:]
        return f"/mnt/{drive}{rest}"
    return path
