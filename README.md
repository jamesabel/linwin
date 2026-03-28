# WSL2 Ubuntu + GNOME GUI Setup

Automated scripts to install Ubuntu with WSLg GUI on Windows 11 via WSL2, with the distro stored on a dedicated SSD drive.

## Prerequisites

- **Windows 11** (or Windows 10 build 19044+)
- **Hardware virtualization** enabled in BIOS/UEFI (Intel VT-x or AMD-V)
- **Dedicated drive** for WSL storage (default: V: drive)
- **Administrator access** on Windows

## Quick Start (TUI)

The recommended way to run the setup is via the interactive TUI (Text User Interface):

```powershell
setup_wsl.bat
```

This launches a full terminal UI with system detection, a configuration editor, step-by-step progress tracking, and a verification dashboard. The TUI handles admin elevation, the reboot boundary, and cross-WSL Linux setup automatically.

A standalone Linux TUI is also available for running inside WSL Ubuntu directly:

```bash
pip3 install textual
python3 setup_tui_linux.py
```

## Quick Start (Scripts)

### Step 1: Enable Windows features (requires reboot)

Right-click `setup_windows_phase1.ps1` > **Run with PowerShell**, or in an admin PowerShell:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\setup_windows_phase1.ps1
```

This validates your system and enables WSL and Virtual Machine Platform. **Reboot when prompted.**

### Step 2: Install Ubuntu and configure everything

After rebooting, run `setup_windows_phase2.ps1` as Administrator:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
.\setup_windows_phase2.ps1
```

This will:
- Install/update WSL2 and Ubuntu 22.04
- Move the distro to your V: drive
- Write optimized `.wslconfig` settings
- Enable systemd inside Ubuntu
- Install IDEs (VS Code, IntelliJ IDEA, PyCharm) and Nautilus file manager via snap
- Verify WSLg is working

### Step 3: Verify

```powershell
.\verify_setup.ps1
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

### TUI (Python Textual)

| Script | Environment | Description |
|--------|-------------|-------------|
| `_setup_tui.py` | Windows | Interactive TUI — guides entire setup with live progress |
| `setup_tui_linux.py` | WSL Ubuntu | Interactive TUI for Linux-side setup (also supports `--headless`) |

### PowerShell / Bash

| Script | Environment | Description |
|--------|-------------|-------------|
| `setup_windows_phase1.ps1` | Windows (admin) | Enable WSL/VM features, prompt reboot |
| `setup_windows_phase2.ps1` | Windows (admin) | Install Ubuntu, move to V:, configure, run Linux setup |
| `_setup_ubuntu.sh` | WSL Ubuntu | Install packages, enable systemd, verify WSLg |
| `verify_setup.ps1` | Windows | Run all verification checks |
| `_verify_setup.sh` | WSL Ubuntu | Linux-side verification checks |

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
