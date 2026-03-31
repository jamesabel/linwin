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
    """Legacy snap package entry. Kept for backward compatibility with install_snap()."""

    name: str
    classic: bool = True


@dataclass
class AppEntry:
    """An optional application that can be selected, installed, and launched.

    Attributes:
        id: Unique identifier, typically the package name (e.g. "pycharm-community").
        display_name: Human-readable name shown in the UI.
        command: Shell command to launch the app inside WSL.
        install_method: How the app is installed — "snap", "apt", or "custom".
            "custom" means the user installs it themselves; linwin only provides
            a launch button.
        classic: Whether to use ``--classic`` flag (snap only).
    """

    id: str
    display_name: str
    command: str
    install_method: str = "snap"  # "snap" | "apt" | "custom"
    classic: bool = True


# Curated registry of well-known optional applications.
# To add a new app, just append an AppEntry line.
APP_REGISTRY: list[AppEntry] = [
    # IDEs
    AppEntry("code",                    "VS Code",                  "code",                     "snap", classic=True),
    AppEntry("pycharm-community",       "PyCharm Community",        "pycharm-community",        "snap", classic=True),
    AppEntry("intellij-idea-community", "IntelliJ IDEA Community",  "intellij-idea-community",  "snap", classic=True),
    # Browsers
    AppEntry("firefox",                 "Firefox",                  "firefox",                  "snap", classic=False),
    AppEntry("chromium",                "Chromium",                 "chromium",                 "snap", classic=False),
    # Editors
    AppEntry("sublime-text",            "Sublime Text",             "subl",                     "snap", classic=True),
    # Graphics
    AppEntry("gimp",                    "GIMP",                     "gimp",                     "snap", classic=False),
    # Office
    AppEntry("libreoffice",             "LibreOffice",              "libreoffice",              "snap", classic=False),
    # Apt-installable apps
    AppEntry("thunderbird",             "Thunderbird",              "thunderbird",              "apt"),
    AppEntry("gedit",                   "Text Editor (gedit)",      "gedit",                    "apt"),
    # Custom-installed apps (launch button only, user installs separately)
    AppEntry("matlab",                  "MATLAB",                   "matlab",                   "custom"),
    AppEntry("mathematica",             "Mathematica",              "mathematica",              "custom"),
]

# Index for fast lookup by ID.
_APP_REGISTRY_MAP: dict[str, AppEntry] = {a.id: a for a in APP_REGISTRY}


# Backward-compat alias used by legacy code / tests.
AVAILABLE_SNAPS: list[tuple[str, str]] = [
    (a.id, a.display_name) for a in APP_REGISTRY if a.install_method == "snap"
]


@dataclass
class SetupConfig:
    distroName: str = "Ubuntu-22.04"
    distroImportName: str = "Ubuntu"
    wslInstallPath: str = "V:\\WSL\\Ubuntu"
    wslDriveLetter: str = "V"
    wslconfig: WslConfig = field(default_factory=WslConfig)
    snaps: list[SnapPackage] = field(default_factory=list)
    optionalApps: list[AppEntry] = field(default_factory=list)
    aptPackages: list[str] = field(default_factory=lambda: ["nautilus", "x11-apps"])
    enableSystemd: bool = True
    xrdpPort: int = 3390

    @staticmethod
    def from_dict(data: dict) -> SetupConfig:
        wslconfig = WslConfig(**data.get("wslconfig", {}))

        # Prefer optionalApps if present; fall back to migrating legacy snaps.
        if "optionalApps" in data:
            optional_apps = [AppEntry(**a) for a in data["optionalApps"]]
        else:
            optional_apps = []
            for s in data.get("snaps", []):
                name = s["name"] if isinstance(s, dict) else s
                classic = s.get("classic", True) if isinstance(s, dict) else True
                reg = _APP_REGISTRY_MAP.get(name)
                optional_apps.append(AppEntry(
                    id=name,
                    display_name=reg.display_name if reg else name,
                    command=reg.command if reg else name,
                    install_method="snap",
                    classic=classic,
                ))

        # Derive snaps from optionalApps for backward-compatible installation.
        snaps = [SnapPackage(a.id, a.classic) for a in optional_apps
                 if a.install_method == "snap"]

        return SetupConfig(
            distroName=data.get("distroName", "Ubuntu-22.04"),
            distroImportName=data.get("distroImportName", "Ubuntu"),
            wslInstallPath=data.get("wslInstallPath", "V:\\WSL\\Ubuntu"),
            wslDriveLetter=data.get("wslDriveLetter", "V"),
            wslconfig=wslconfig,
            snaps=snaps,
            optionalApps=optional_apps,
            aptPackages=data.get("aptPackages", ["nautilus", "x11-apps"]),
            enableSystemd=data.get("enableSystemd", True),
            xrdpPort=data.get("xrdpPort", 3390),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        # Keep snaps derived from optionalApps for backward compat.
        d["snaps"] = [{"name": a.id, "classic": a.classic}
                      for a in self.optionalApps if a.install_method == "snap"]
        return d


def get_config_path(script_path: str | None = None) -> Path:
    """Find config.json by searching several locations.

    Search order:
    1. Next to the given *script_path* (if provided).
    2. The current working directory.
    3. Next to ``sys.executable`` (covers frozen/pyship builds).
    4. Walking up from this source file (covers dev/repo layouts).
    """
    import sys

    if script_path:
        p = Path(script_path).resolve().parent / "config.json"
        if p.exists():
            return p

    # Current working directory
    cwd_candidate = Path.cwd() / "config.json"
    if cwd_candidate.exists():
        return cwd_candidate

    # Next to the Python executable (frozen / pyship builds)
    exe_candidate = Path(sys.executable).resolve().parent / "config.json"
    if exe_candidate.exists():
        return exe_candidate

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


def collect_app_selections(query_one_fn, registry: list[AppEntry] | None = None) -> list[AppEntry]:
    """Read app checkbox values from the UI and return selected AppEntries.

    Args:
        query_one_fn: Callable that resolves a CSS selector to a widget
                      (typically ``screen.query_one``).
        registry: App list to iterate; defaults to ``APP_REGISTRY``.
    """
    from .widgets import AsciiCheckbox

    if registry is None:
        registry = APP_REGISTRY
    selected = []
    for app in registry:
        cb = query_one_fn(f"#app-{app.id}", AsciiCheckbox)
        if cb.value:
            selected.append(app)
    return selected


def parse_apt_input(raw: str) -> list[str]:
    """Parse a comma-separated apt package string into a clean list."""
    return [p.strip() for p in raw.split(",") if p.strip()]


def windows_to_wsl_path(win_path: str) -> str:
    """Convert C:\\foo\\bar to /mnt/c/foo/bar."""
    path = win_path.replace("\\", "/")
    if len(path) >= 2 and path[1] == ":":
        drive = path[0].lower()
        rest = path[2:]
        return f"/mnt/{drive}{rest}"
    return path
