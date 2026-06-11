# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

linwin is a Textual-based TUI that automates installing Ubuntu on Windows 11 via WSL2 — storing the distro on a dedicated drive, enabling WSLg for GUI apps, and configuring xrdp + XFCE4 for full-desktop Remote Desktop access. It runs **two TUIs**: a Windows-side orchestrator and a Linux-side setup tool invoked across the WSL boundary.

## Commands

All commands use `uv` and run from the project root.

- **Run the Windows TUI:** `uv run python -m linwin.windows` (or `run.bat`)
- **Dev environment setup:** `scripts\setup_dev.bat` (installs uv, Python, syncs runtime + `dev` group)
- **Full end-user setup:** `scripts\setup_wsl.bat` (also installs uv/Python; uses `uv sync --exclude-newer <7 days ago>` for supply-chain safety)
- **Run all tests:** `uv run python -m pytest tests/ -v` (or `scripts\test.bat`)
- **Run one test:** `uv run python -m pytest tests/test_config.py::test_name -v`
- **Run with coverage:** `uv run python -m pytest tests/ --cov=linwin --cov-report=term-missing`
- **Build frozen exe + NSIS installer:** `scripts\ship.bat` (pyship — deletes `dist/`, `app/`, `*.nsi` first since they're stale build artifacts)
- **Publish to PyPI:** `scripts\publish.bat` (uv build + twine; needs a PyPI token in keyring)

**Linux TUI** (runs inside WSL, where `pref` is typically not installed so config falls back to defaults):
- Interactive: `python3 -m linwin.linux`
- Headless (how the Windows side drives it): `python3 -m linwin.linux --headless --step {enable-systemd|install-packages|configure-xrdp}`

**Test caveats:** the `test_rdp_*` modules execute real `wsl.exe` commands — but against a dedicated clone of the configured distro (named `linwin-test`, created automatically by `tests/conftest.py` on first use via export/import, xrdp shifted to port 3391 / sesman 3351 because all WSL2 distros share one network namespace). They never touch the real distro; they skip if no source distro exists to clone. Rebuild the clone with `wsl --unregister linwin-test`; override via `LINWIN_TEST_DISTRO`. Tests use `pytest-asyncio`; async subprocess coros are driven via the `_run` helper in `tests/helpers.py`.

## Architecture

Three packages under `linwin/`:

- **`linwin/windows/`** — the orchestrator TUI. Entry: `python -m linwin.windows`. Starts as a standard user; elevates per-operation via UAC only when needed (see below).
- **`linwin/linux/`** — the WSL-side TUI/headless runner that does all Linux configuration (systemd, apt, snaps, xrdp).
- **`linwin/shared/`** — config, subprocess runner, base app/screen, widgets, theme, logging, the headless protocol — imported by both sides.

Each side follows the same internal split: `screens/` (Textual UI) call into `tasks/` (async business logic returning `TaskResult`). Keep UI and task logic separate — screens orchestrate and render; tasks run subprocesses and return results.

### The cross-WSL boundary (most important concept)

The Windows orchestrator cannot run Linux setup directly — it invokes the Linux package *inside WSL* as a subprocess and parses its output:

`windows/screens/setup.py` → `windows/tasks/linux_invoke.py` → `wsl.exe -d <distro> -- python3 -m linwin.linux --headless --step <step>` → `linux/__main__.py` headless handlers → `linux/tasks/*`.

Communication uses the **structured headless protocol** in `shared/headless_protocol.py`: the Linux side prints `TASK:<id>:<status>`, `LOG:<msg>`, and `ERROR:<msg>` lines; the Windows side parses them back into TUI task-status updates and log lines. When changing what the Linux headless steps emit, update both the `emit_*` producers and `parse_headless_line` consumer together.

### Setup as a resumable task list

`windows/screens/setup.py` defines `SETUP_TASKS` — a flat ordered list of all setup steps (Windows feature enables → WSL install/export/import → Linux systemd/packages/xrdp). The whole flow is one Textual `@work` coroutine that runs tasks in order, each guarded by `if start_index <= task_ids.index(...)`.

Enabling Windows features (DISM) requires a **reboot**. At that checkpoint the flow saves `SetupState(resume_from_task="update_wsl")` to `%LOCALAPPDATA%\linwin\setup_state.json` and stops. On next launch, `windows/app.py` `on_mount` detects the saved state and jumps `SetupScreen` straight to the resume point, marking earlier tasks done. `clear_state()` runs on completion. If you add/reorder tasks, keep `RESUME_AFTER_REBOOT` pointing at the correct post-reboot task id.

### App startup flow

`windows/app.py` `on_mount`: if resuming → `SetupScreen`; otherwise run full verification (`tasks/full_verify.py`). All checks pass → `LauncherScreen`. Failures → auto-detect hardware (`tasks/auto_config.py`) and show `SetupProposalScreen` with recommended config (memory = RAM÷4, cpus = CPUs÷2, best drive by NVMe > SSD > HDD).

### Configuration

`SetupConfig` (in `shared/config.py`) is the single config dataclass. On Windows it's persisted in a per-user **sqlite DB via the `pref` package** (not a JSON file — `config.json` was removed). The Linux side receives config as a dict over the boundary and never touches the DB. `SetupConfig.from_dict`/`to_dict` handle (de)serialization and migrate the legacy `snaps` field into the `optionalApps` / `APP_REGISTRY` model. To add a launchable app, append one `AppEntry` to `APP_REGISTRY`.

### Subprocess execution

All process calls go through `shared/subprocess_runner.py` (`run_command` and wrappers `run_powershell`, `run_wsl`, `run_wsl_exec`, `run_local`). It's async, streams output line-by-line to an `on_line` callback, strips null bytes from `wsl.exe` output, and logs every command. Prefer these over raw `subprocess`. Note `run_wsl` takes a `cwd=` (passed to `wsl.exe --cd`) to avoid `&&` parsing issues — don't build `cd '...' &&` command strings.

### Admin elevation

The app deliberately launches **without** admin. `windows/app.py` `run_elevated()` elevates a *single* command via PowerShell `Start-Process -Verb RunAs -Wait` (used for DISM feature enables) rather than relaunching the whole app elevated. RDP connects directly to the WSL2 VM's NAT IP (`shared/launcher.py`), avoiding an admin-requiring netsh port proxy.

### Keepalive

WSL2 tears down the VM when the last `wsl.exe` process exits, which would kill xrdp sessions. `shared/launcher.py` `ensure_wsl_keepalive` holds a hidden background `sleep infinity` process open so the VM survives after the TUI exits.

### Conventions

- Tasks return `TaskResult(ok, message, skipped=..., detail=..., needs_restart=...)` (`shared/task_result.py`). The runner in `setup.py` and `linux/__main__.py` both branch on `ok`/`skipped`.
- Shared screens subclass `ClickDispatchScreen` (base_app.py) and declare a `CLICK_MAP` of widget-id → action-method-name instead of writing `on_click` branches; keybindings map number keys to the same actions.
- Logs go to `%LOCALAPPDATA%\linwin\logs\setup.log` (Windows) / `~/.local/share/linwin/logs/setup.log` (Linux), rotating. Get the logger via `get_logger()`.
- `xrdpPort` defaults to **3390** (not 3389) to avoid colliding with Windows' own RDP.
- `app/` and `dist/` are gitignored pyship build artifacts — ignore them; the real source is `linwin/`.
