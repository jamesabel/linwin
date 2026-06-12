# linwin

[![CI](https://github.com/jamesabel/linwin/actions/workflows/ci.yml/badge.svg)](https://github.com/jamesabel/linwin/actions/workflows/ci.yml)

Automated TUI (Text User Interface) to install Ubuntu on Windows 11 via WSL2, with the distro stored on a dedicated SSD drive. Includes WSLg for seamless Linux GUI apps on Windows and xrdp for full XFCE4 desktop access via Remote Desktop — including snap apps like Firefox, which need special handling to work over RDP.

## Prerequisites

- **Windows 11** (or Windows 10 build 19044+)
- **Hardware virtualization** enabled in BIOS/UEFI (Intel VT-x or AMD-V)
- **Ability to elevate (UAC)** — the app runs as a standard user and prompts for elevation only when enabling Windows features

## Quick Start

```powershell
scripts\setup_wsl.bat
```

This launches an interactive terminal UI that:

- Auto-detects system hardware (RAM, CPUs, drives) and proposes an optimized configuration
- Scans drives and recommends the best one for WSL storage (NVMe > SSD > HDD)
- Runs startup verification and shows any issues before setup begins
- Lets you review and adjust all settings (distro, resources, packages, optional apps)
- Enables WSL and Virtual Machine Platform features (elevating per-command via UAC)
- Installs Ubuntu, exports/imports to your chosen drive
- Creates the default Linux user with passwordless sudo and prompts you to set the RDP password
- Writes `.wslconfig` with your resource limits
- Runs Linux-side setup (systemd, apt packages, snap/apt optional apps, xrdp)
- Configures xrdp with XFCE4 desktop for Remote Desktop access, a working default
  web browser, and desktop shortcuts for your selected apps
- Shows live progress throughout: per-task status with elapsed time, streaming
  command output, and reasons for any skipped step
- Maintains a WSL keepalive process to prevent VM shutdown between sessions
- Verifies everything with a PASS/FAIL dashboard (copyable to the clipboard)

The TUI handles admin elevation, the reboot boundary, and cross-WSL Linux setup automatically. After setup, a launcher screen lets you open apps, launch a terminal, connect via Remote Desktop, or run maintenance tasks (re-verify, reconfigure, reset the RDP password).

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

A headless mode is available for non-interactive automation (this is how the
Windows side drives Linux setup, passing the configuration as base64 JSON):

```bash
python3 -m linwin.linux --headless --step enable-systemd
python3 -m linwin.linux --headless --step install-packages
python3 -m linwin.linux --headless --step configure-xrdp
```

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| 1-9 | Select numbered actions (maintenance, setup screens) |
| a-z | Launch apps / actions on the launcher and verify screens |
| Escape | Quit app / Cancel current screen |
| Ctrl+Q | Quit app |
| Ctrl+C | Copy the current screen's log or results to the clipboard |
| Click | Select action links and options |

## Configuration

Configuration is stored in a per-user sqlite database (via the `pref` package) and edited with the built-in Configure Settings screen. On first launch, the TUI auto-detects your system profile and proposes sensible defaults:

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
| `optionalApps` | *(empty)* | Apps to install and launch (VS Code, PyCharm, Firefox, GIMP, OpenClaw, ...) — pick from the curated registry in the editor |
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
| `linwin/shared/` | Shared widgets, config, theme, headless protocol, and subprocess utilities |
| `tests/` | pytest test suite (410 tests; see Testing below) |

## Setup Phases

**Startup:** Auto-detects system hardware, runs verification checks (concurrently, in a few seconds), and presents a setup proposal with recommended configuration for user approval.

**Phase 1 (Windows):** Validates prerequisites, enables WSL and Virtual Machine Platform features via UAC-elevated DISM, prompts for reboot if needed and resumes automatically after it.

**Phase 2 (Windows + Linux):** Updates WSL, installs Ubuntu, exports/imports the distro to the target drive, sets up the default user (sudo, RDP password), writes `.wslconfig`, enables systemd, installs apt and snap packages non-interactively, configures xrdp with XFCE4 desktop, default browser, and desktop shortcuts.

**Verification:** Checks all Windows features, distro registration, WSL version, systemd, packages, WSLg display, xrdp service, and drive mounts. Results can be copied to the clipboard.

## Testing

```powershell
scripts\test.bat                                          # everything
uv run python -m pytest tests/ --cov=linwin               # with coverage
```

Most of the suite is mocked and runs in seconds (it's what CI runs). The `test_rdp_*` modules are live end-to-end tests — RDP login, session stability, desktop interaction — that run against a **dedicated clone** of your configured distro: created at the start of the session via export/import, isolated on its own ports and display range, and unregistered at the end so the disk space is reclaimed. They never touch your real distro and skip when there's no distro to clone. Set `LINWIN_TEST_KEEP=1` to keep the clone between runs for faster iteration.

## OpenClaw Agent

Select **OpenClaw (AI agent)** in Configure Settings and re-run setup to install the [OpenClaw](https://openclaw.ai) personal AI agent inside WSL via its official installer (Node.js is handled automatically). Setup enables the gateway as a systemd user service with lingering, so it keeps running with no terminal open. To finish configuration (model API keys, chat channels), run once in an Ubuntu terminal:

```bash
openclaw onboard
```

The dashboard is then available from Windows at `http://localhost:18789`. To keep the agent running across Windows reboots, use **Maintenance → Toggle WSL Autostart at Logon** in the launcher — it creates a per-user scheduled task (no admin needed) that boots the distro at logon; the lingering gateway service does the rest. A browser from the registry (e.g. Firefox) is recommended alongside OpenClaw for its browsing features and the dashboard.

Useful commands inside Ubuntu:

```bash
openclaw gateway status      # is the agent running?
openclaw doctor              # diagnose installation issues
openclaw update              # update to the latest version
systemctl --user status openclaw-gateway   # the underlying service
```

> **Security note:** OpenClaw is a powerful agent — it can read files, run
> commands, and act on connected chat channels on your behalf. It runs inside
> your WSL distro under your Linux user. Review its
> [security guidance](https://docs.openclaw.ai/gateway/security) before
> connecting channels or granting API keys, and treat the gateway dashboard
> (localhost-only by default) accordingly.

## Detailed Guide

See [wsl_ubuntu_gnome.md](wsl_ubuntu_gnome.md) for the full manual guide with GUI comparison (WSLg vs. external X servers), troubleshooting, security notes, and decision checklist.

## Launching Apps

After setup, use the launcher screen to open apps directly, or pick "RDP into Ubuntu" to open the full XFCE4 desktop (it resolves the WSL VM address and starts a keepalive for you). To connect manually:

```powershell
mstsc /v:127.0.0.1:3390
```

Log in with your Linux username and the password set during setup (forgot it? the launcher's Maintenance section has "Reset RDP Password"). Your selected optional apps have icons on the XFCE desktop, and snap apps like Firefox work inside the RDP session.

Individual apps can also be launched from an Ubuntu terminal:

```bash
nautilus &                   # File Manager
```

Apps appear as native Windows windows via WSLg. A background keepalive process ensures the WSL VM stays running between app launches.
