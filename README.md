# WSL2 Ubuntu + GNOME GUI Setup

Automated scripts to install Ubuntu with WSLg GUI on Windows 11 via WSL2, with the distro stored on a dedicated SSD drive.

## Prerequisites

- **Windows 11** (or Windows 10 build 19044+)
- **Hardware virtualization** enabled in BIOS/UEFI (Intel VT-x or AMD-V)
- **Dedicated drive** for WSL storage (default: V: drive)
- **Administrator access** on Windows

## Quick Start

Run the setup via the interactive TUI (Text User Interface):

```powershell
setup_wsl.bat
```

This launches a full terminal UI with system detection, a configuration editor, step-by-step progress tracking, and a verification dashboard. The TUI handles admin elevation, the reboot boundary, and cross-WSL Linux setup automatically.

A standalone Linux TUI is also available for running inside WSL Ubuntu directly:

```bash
pip3 install textual
python3 setup_tui_linux.py
```

## Configuration

Edit `config.json` before running the scripts to customize:

| Field | Default | Description |
|-------|---------|-------------|
| `distroName` | `Ubuntu-22.04` | Distro to install via `wsl --install` |
| `distroImportName` | `Ubuntu` | Name after export/import to V: drive |
| `wslInstallPath` | `V:\WSL\Ubuntu` | Where to store the distro VHD |
| `wslDriveLetter` | `V` | Drive letter for WSL storage |
| `wslconfig.memory` | `16GB` | RAM limit for WSL2 |
| `wslconfig.processors` | `8` | CPU cores for WSL2 |
| `wslconfig.swap` | `8GB` | Swap size |
| `wslconfig.defaultVhdSize` | `200GB` | Max VHD size |
| `snaps` | VS Code, IntelliJ, PyCharm | Snap packages to install |
| `aptPackages` | nautilus, x11-apps | Apt packages to install |

## Scripts

| Script | Environment | Description |
|--------|-------------|-------------|
| `setup_wsl.bat` | Windows | Entry point — installs dependencies, then launches the TUI |
| `_setup_tui.py` | Windows | Interactive TUI — guides entire setup with live progress |
| `setup_tui_linux.py` | WSL Ubuntu | Interactive TUI for Linux-side setup (also supports `--headless`) |

## Detailed Guide

See [wsl_ubuntu_gnome.md](wsl_ubuntu_gnome.md) for the full manual guide with GUI comparison (WSLg vs. external X servers), troubleshooting, security notes, and decision checklist.

## Launching Apps

After setup, open Ubuntu and run:

```bash
code &                       # VS Code
intellij-idea-community &    # IntelliJ IDEA
pycharm-community &          # PyCharm
nautilus &                   # File Manager
```

Apps appear as native Windows windows via WSLg.
