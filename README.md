# linwin

Automated TUI (Text User Interface) to install Ubuntu on Windows 11 via WSL2, with the distro stored on a dedicated SSD drive. Includes WSLg for seamless Linux GUI apps on Windows and xrdp for full XFCE4 desktop access via Remote Desktop.

## Prerequisites

- **Windows 11** (or Windows 10 build 19044+)
- **Hardware virtualization** enabled in BIOS/UEFI (Intel VT-x or AMD-V)
- **Administrator access** on Windows

## Quick Start

```powershell
scripts\setup_wsl.bat
```

This launches an interactive terminal UI that:

- Auto-detects system hardware (RAM, CPUs, drives) and proposes an optimized configuration
- Scans drives and recommends the best one for WSL storage (NVMe > SSD > HDD)
- Runs startup verification and shows any issues before setup begins
- Lets you review and adjust all settings (distro, resources, packages)
- Enables WSL and Virtual Machine Platform features
- Installs Ubuntu, exports/imports to your chosen drive
- Writes `.wslconfig` with your resource limits
- Runs Linux-side setup (systemd, apt packages, snap packages, xrdp)
- Configures xrdp with XFCE4 desktop for Remote Desktop access
- Maintains a WSL keepalive process to prevent VM shutdown between sessions
- Verifies everything with a PASS/FAIL dashboard

The TUI handles admin elevation, the reboot boundary, and cross-WSL Linux setup automatically. After setup, a launcher screen lets you open apps, launch a terminal, or connect via Remote Desktop.

For quick reruns without dependency installation:

```powershell
linwin.bat
```

### Linux TUI

A standalone Linux TUI is also available for running inside WSL Ubuntu directly:

```bash
pip3 install textual
python3 -m linwin.linux
```

A headless mode is available for non-interactive automation:

```bash
python3 -m linwin.linux --headless --step enable-systemd
python3 -m linwin.linux --headless --step install-packages
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| 1-9 | Select numbered actions on any screen |
| Escape | Quit app / Cancel current screen |
| Ctrl+Q | Quit app |
| Click | Select action links and options |

## Configuration

Edit `config.json` before running, or use the built-in Configure Settings screen. On first launch, the TUI auto-detects your system profile and proposes sensible defaults:

| Field | Default | Description |
|-------|---------|-------------|
| `distroName` | `Ubuntu-22.04` | Distro to install via `wsl --install` |
| `distroImportName` | `Ubuntu` | Name after export/import |
| `wslInstallPath` | auto-detected | Where to store the distro VHD |
| `wslDriveLetter` | auto-detected | Best available drive (NVMe > SSD > HDD) |
| `wslconfig.memory` | RAM ÷ 4 | RAM limit for WSL2 (min 4 GB) |
| `wslconfig.processors` | CPUs ÷ 2 | CPU cores for WSL2 (min 1) |
| `wslconfig.swap` | RAM ÷ 8 | Swap size (min 4 GB) |
| `wslconfig.defaultVhdSize` | `512GB` | Max VHD size |
| `snaps` | *(empty)* | Snap packages to install (configure via editor) |
| `aptPackages` | nautilus, x11-apps, xfce4, xfce4-terminal, xrdp, dbus-x11 | Apt packages to install |
| `xrdpPort` | `3390` | Port for xrdp (avoids conflict with Windows RDP on 3389) |

## Project Structure

| Path | Description |
|------|-------------|
| `linwin.bat` | Quick launch -- runs the TUI without dependency installation |
| `scripts/setup_wsl.bat` | Full setup -- installs uv, Python, dependencies, then launches the TUI |
| `scripts/test.bat` | Run the test suite |
| `linwin/windows/` | Windows TUI package -- startup verification, auto-config, setup with live progress |
| `linwin/linux/` | Linux TUI package for WSL-side setup (also supports `--headless`) |
| `linwin/shared/` | Shared widgets, config, theme, and subprocess utilities |
| `tests/` | pytest test suite (106 tests) |
| `config.json` | Default configuration |

## Setup Phases

**Startup:** Auto-detects system hardware, runs verification checks, and presents a setup proposal with recommended configuration for user approval.

**Phase 1 (Windows):** Validates prerequisites, enables WSL and Virtual Machine Platform features, prompts for reboot if needed.

**Phase 2 (Windows + Linux):** Updates WSL, installs Ubuntu, exports/imports distro to target drive, writes `.wslconfig`, enables systemd, installs apt and snap packages, configures xrdp with XFCE4 desktop.

**Verification:** Checks all Windows features, distro registration, WSL version, systemd, packages, WSLg display, xrdp service, and drive mounts.

## Detailed Guide

See [wsl_ubuntu_gnome.md](wsl_ubuntu_gnome.md) for the full manual guide with GUI comparison (WSLg vs. external X servers), troubleshooting, security notes, and decision checklist.

## Launching Apps

After setup, use the launcher screen to open apps directly, or connect via Remote Desktop:

```powershell
mstsc /v:127.0.0.1:3390
```

Individual apps can also be launched from an Ubuntu terminal:

```bash
nautilus &                   # File Manager
```

Apps appear as native Windows windows via WSLg. A background keepalive process ensures the WSL VM stays running between app launches.
