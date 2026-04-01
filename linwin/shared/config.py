"""Shared configuration: dataclasses, app registry, sqlite-backed persistence via pref.

The ``pref`` package is only required on Windows where the sqlite config
database lives.  Linux headless mode receives config from the Windows
side and never touches the DB directly.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ── Data classes ─────────────────────────────────────────────────────


@dataclass
class WslConfig:
    """Resource limits written to ~/.wslconfig."""

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


# ── App registry ─────────────────────────────────────────────────────


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


# ── SetupConfig ──────────────────────────────────────────────────────


@dataclass
class SetupConfig:
    """All user-configurable settings for WSL2 Ubuntu setup."""

    distroName: str = "Ubuntu-22.04"
    distroImportName: str = "Ubuntu"
    wslInstallPath: str = "V:\\WSL\\Ubuntu"
    wslDriveLetter: str = "V"
    wslconfig: WslConfig = field(default_factory=WslConfig)
    snaps: list[SnapPackage] = field(default_factory=list)
    optionalApps: list[AppEntry] = field(default_factory=list)
    aptPackages: list[str] = field(default_factory=lambda: [
        "nautilus", "x11-apps", "xfce4", "xfce4-terminal", "xrdp", "dbus-x11",
    ])
    enableSystemd: bool = True
    xrdpPort: int = 3390

    @staticmethod
    def from_dict(data: dict) -> SetupConfig:
        """Deserialize from a plain dict (JSON-style)."""
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
            aptPackages=data.get("aptPackages", [
                "nautilus", "x11-apps", "xfce4", "xfce4-terminal", "xrdp", "dbus-x11",
            ]),
            enableSystemd=data.get("enableSystemd", True),
            xrdpPort=data.get("xrdpPort", 3390),
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dict."""
        d = asdict(self)
        d["snaps"] = [{"name": a.id, "classic": a.classic}
                      for a in self.optionalApps if a.install_method == "snap"]
        return d


# ── SQLite-backed persistence via pref ───────────────────────────────

_APPLICATION_NAME = "linwin"
_APPLICATION_AUTHOR = "abel"


def _config_to_pref_dict(config: SetupConfig) -> dict[str, str | int | bool]:
    """Convert SetupConfig to flat key-value pairs for pref storage.

    Complex fields (WslConfig, lists) are JSON-encoded strings.
    """
    return {
        "distroName": config.distroName,
        "distroImportName": config.distroImportName,
        "wslInstallPath": config.wslInstallPath,
        "wslDriveLetter": config.wslDriveLetter,
        "wslconfig": json.dumps(asdict(config.wslconfig)),
        "optionalApps": json.dumps([asdict(a) for a in config.optionalApps]),
        "aptPackages": json.dumps(config.aptPackages),
        "enableSystemd": int(config.enableSystemd),
        "xrdpPort": config.xrdpPort,
    }


def _pref_dict_to_config(data: dict) -> SetupConfig:
    """Reconstruct SetupConfig from flat pref key-value pairs."""
    wslconfig_raw = data.get("wslconfig", "{}")
    wslconfig = WslConfig(**json.loads(wslconfig_raw)) if isinstance(wslconfig_raw, str) else WslConfig()

    optional_raw = data.get("optionalApps", "[]")
    optional_apps = [AppEntry(**a) for a in json.loads(optional_raw)] if isinstance(optional_raw, str) else []

    apt_raw = data.get("aptPackages", "[]")
    apt_packages = json.loads(apt_raw) if isinstance(apt_raw, str) else [
        "nautilus", "x11-apps", "xfce4", "xfce4-terminal", "xrdp", "dbus-x11",
    ]

    snaps = [SnapPackage(a.id, a.classic) for a in optional_apps if a.install_method == "snap"]

    enable_systemd = data.get("enableSystemd", 1)
    if isinstance(enable_systemd, int):
        enable_systemd = bool(enable_systemd)

    return SetupConfig(
        distroName=data.get("distroName", "Ubuntu-22.04"),
        distroImportName=data.get("distroImportName", "Ubuntu"),
        wslInstallPath=data.get("wslInstallPath", "V:\\WSL\\Ubuntu"),
        wslDriveLetter=data.get("wslDriveLetter", "V"),
        wslconfig=wslconfig,
        snaps=snaps,
        optionalApps=optional_apps,
        aptPackages=apt_packages,
        enableSystemd=enable_systemd,
        xrdpPort=data.get("xrdpPort", 3390),
    )


def load_config(db_path: Path | None = None) -> SetupConfig:
    """Load configuration from the per-user sqlite database.

    If the database doesn't exist or is empty, initializes with defaults.

    Args:
        db_path: Override the DB file path (for testing). If None, uses
                 the platform default user config directory.
    """
    p = _open_pref(db_path)
    data = dict(p.get_sqlite_dict())

    # Strip pref internal keys.
    data = {k: v for k, v in data.items() if not k.startswith("_")}

    if data:
        return _pref_dict_to_config(data)

    # DB is empty — initialize with defaults and persist them.
    config = SetupConfig()
    save_config(config, db_path)
    return config


def save_config(config: SetupConfig, db_path: Path | None = None) -> None:
    """Save configuration to the per-user sqlite database.

    Args:
        db_path: Override the DB file path (for testing).
    """
    p = _open_pref(db_path)
    sd = p.get_sqlite_dict()
    for key, value in _config_to_pref_dict(config).items():
        sd[key] = value
    sd.commit()


def _open_pref(db_path: Path | None = None):
    """Open the pref database, optionally at a custom path."""
    from pref import Pref
    if db_path is not None:
        return Pref(_APPLICATION_NAME, _APPLICATION_AUTHOR, file_name=str(db_path.name))
    return Pref(_APPLICATION_NAME, _APPLICATION_AUTHOR)


def get_config_db_path() -> Path:
    """Return the path to the sqlite config database (for display purposes)."""
    from pref import Pref
    p = Pref(_APPLICATION_NAME, _APPLICATION_AUTHOR)
    return p.get_sqlite_path()




# ── Validation ───────────────────────────────────────────────────────


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


# ── UI helpers ───────────────────────────────────────────────────────


def collect_app_selections(query_one_fn, registry: list[AppEntry] | None = None) -> list[AppEntry]:
    """Read app checkbox values from the UI and return selected AppEntries."""
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
