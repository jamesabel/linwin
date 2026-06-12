"""Windows TUI Setup Screen — single unified flow for all setup tasks."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from ...shared.base_app import ClickDispatchScreen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.setup_logging import get_logger
from ...shared.widgets import LogPanel, TaskListWidget
from ..tasks import features, validators, wsl_install
from ..tasks.linux_invoke import run_linux_headless
from ..tasks.setup_tasks import RESUME_AFTER_REBOOT, SETUP_TASKS, TASK_IDS
from ..tasks.state import SetupState, clear_state, save_state
from ..tasks.wsl_config import write_wslconfig


class SetupScreen(ClickDispatchScreen):
    """Single setup screen that runs all tasks, pausing for reboot only when needed."""

    BINDINGS = [
        ("1", "reboot", "Reboot"),
        ("2", "verify", "Verify"),
        ("3", "launcher", "Launcher"),
    ]

    CLICK_MAP = {
        "btn-reboot": "reboot",
        "btn-verify": "verify",
        "btn-launcher": "launcher",
    }

    CSS = """
    #setup-status {
        padding: 1 2;
        text-style: bold;
        color: $text;
    }
    #btn-verify {
        color: $success;
    }
    #btn-reboot {
        color: $warning;
    }
    #btn-launcher {
        color: $accent;
    }
    """

    def __init__(self, config: SetupConfig, resume_from: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._resume_from = resume_from
        self._needs_reboot = False

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            yield TaskListWidget(SETUP_TASKS, id="setup-tasks")
            yield LogPanel(id="setup-log")
            yield Static("", id="setup-status")
            with Horizontal(classes="button-bar"):
                yield Static("\\[1] Reboot Now", id="btn-reboot", classes="action-link hidden")
                yield Static("\\[2] Run Verification", id="btn-verify", classes="action-link hidden")
                yield Static("\\[3] Go to Launcher", id="btn-launcher", classes="action-link hidden")

    def on_mount(self) -> None:
        self.run_setup()

    @work(exclusive=True)
    async def run_setup(self) -> None:
        flog = get_logger()
        flog.info("=== Setup started ===")
        tasks = self.query_one("#setup-tasks", TaskListWidget)
        log = self.query_one("#setup-log", LogPanel)
        status = self.query_one("#setup-status", Static)
        config = self._config

        # Determine resume point
        if self._resume_from and self._resume_from in TASK_IDS:
            start_index = TASK_IDS.index(self._resume_from)
            for i in range(start_index):
                tasks.set_status(TASK_IDS[i], "done")
            log.write_info("Resuming after reboot...")
            flog.info("Resuming from task %s (index %d)", self._resume_from, start_index)
        else:
            start_index = 0

        on_line = log.as_line_callback

        # Helper for simple TaskResult-returning task execution
        async def run_task(task_id: str, coro, fail_msg: str = "") -> bool:
            tasks.set_status(task_id, "running")
            result = await coro
            if result.skipped:
                tasks.set_status(task_id, "skipped", result.message)
                log.write_info(f"Skipped: {result.message}")
            elif result.ok:
                tasks.set_status(task_id, "done")
                if result.message:
                    log.write_success(result.message)
            else:
                tasks.set_status(task_id, "failed")
                log.write_error(fail_msg or result.message)
                return False
            return True

        # ── Step implementations ─────────────────────────────────
        # Each returns True to continue the flow, False to abort.

        def validator_step(task_id: str, label: str, check_coro_factory, abort_msg: str):
            async def step() -> bool:
                tasks.set_status(task_id, "running")
                log.write_command(label)
                result = await check_coro_factory()
                tasks.set_status(task_id, "done" if result.ok else "failed")
                if not result.ok:
                    log.write_error(f"FAILED: {result.message}")
                    if result.detail:
                        for detail_line in result.detail.splitlines():
                            log.write_error(detail_line)
                    status.update(abort_msg)
                    return False
                return True
            return step

        def feature_step(check_id: str, enable_id: str, feature_name: str, enable_fn, label: str):
            async def step() -> bool:
                tasks.set_status(check_id, "running")
                log.write_command(f"Checking {label}...")
                enabled = await features.check_feature(feature_name, on_line)
                if enabled:
                    tasks.set_status(check_id, "done")
                else:
                    tasks.set_status(check_id, "skipped", f"{label} not enabled yet")

                if enabled:
                    tasks.set_status(enable_id, "skipped", f"{label} already enabled")
                    log.write_info(f"{label} already enabled.")
                    return True

                tasks.set_status(enable_id, "running")
                log.write_info(f"Enabling {label} requires administrator access...")
                log.write_command(f"Enabling {label} via DISM...")
                fr = await enable_fn(on_line)
                tasks.set_status(enable_id, "done" if fr.ok else "failed")
                if not fr.ok:
                    log.write_error(f"FAILED: {fr.error}")
                    status.update(f"[red]Failed to enable {label}.[/]")
                    return False
                self._needs_reboot = True
                return True
            return step

        async def update_wsl_step() -> bool:
            log.write_command("wsl --update")
            if not await run_task("update_wsl", wsl_install.update_wsl(on_line), "WSL update failed"):
                status.update("[red]WSL update failed.[/]")
                return False
            return True

        async def set_version_step() -> bool:
            log.write_command("wsl --set-default-version 2")
            if not await run_task("set_version", wsl_install.set_wsl_default_version(on_line)):
                status.update("[red]Failed to set WSL version.[/]")
                return False
            return True

        async def install_distro_step() -> bool:
            log.write_command(f"Installing {config.distroName}...")
            if not await run_task("install_distro", wsl_install.install_distro(config, on_line)):
                status.update("[red]Failed to install distro.[/]")
                return False
            return True

        async def export_import_step() -> bool:
            log.write_command("Exporting distro...")
            tasks.set_status("export_distro", "running")
            export_result, tar_path = await wsl_install.export_distro(config, on_line)
            if export_result.skipped:
                tasks.set_status("export_distro", "skipped", "distro already on target drive")
                tasks.set_status("import_distro", "skipped", "distro already on target drive")
                log.write_info("Distro already on target drive.")
                return True
            if not export_result.ok:
                tasks.set_status("export_distro", "failed")
                log.write_error(export_result.message)
                status.update("[red]Failed to export distro.[/]")
                return False
            tasks.set_status("export_distro", "done")
            log.write_success(export_result.message)

            log.write_command(f"Importing distro to {config.wslInstallPath}...")
            if not await run_task("import_distro", wsl_install.import_distro(config, tar_path, on_line)):
                status.update("[red]Failed to import distro.[/]")
                return False
            return True

        async def set_user_step() -> bool:
            log.write_command("Detecting and setting default user...")
            tasks.set_status("set_user", "running")
            # A valid non-root default already set in wsl.conf wins —
            # that's who the headless steps run as, so sudo must be
            # granted to them, not to whichever /home entry happens to
            # sort first. A default of root, or one with no passwd entry
            # (which breaks every wsl.exe call with getpwnam errors), is
            # treated as unconfigured so set_default_user replaces it.
            username = None
            configured = await wsl_install.get_configured_default_user(config, on_line)
            if configured and configured != "root":
                if await wsl_install.user_exists(config, configured, on_line):
                    username = configured
                    log.write_info(f"Default user already configured: {username}")
                else:
                    log.write_info(f"wsl.conf default '{configured}' has no account — selecting a valid user...")
            elif configured == "root":
                log.write_info("wsl.conf default is root — switching to a non-root user...")

            if username:
                pass
            elif username := await wsl_install.detect_default_user(config, on_line):
                log.write_info(f"Detected user: {username}")
            else:
                # --no-launch skips the OOBE, so create the user ourselves.
                log.write_info("No user found in /home/. Creating default user 'ubuntu'...")
                create_result = await wsl_install.create_default_user(config, "ubuntu", on_line)
                if create_result.ok:
                    username = "ubuntu"
                    log.write_success(create_result.message)
                else:
                    tasks.set_status("set_user", "skipped", "could not create a user — default stays root")
                    log.write_error(create_result.message)
                    log.write_info("Could not create a user. Default user will be root.")
                    return True

            # Headless Linux steps run sudo with no tty — passwordless
            # sudo must be in place before the default user switches away
            # from root, or every later sudo fails.
            sudo_result = await wsl_install.ensure_passwordless_sudo(config, username, on_line)
            if sudo_result.ok:
                if not sudo_result.skipped:
                    log.write_success(sudo_result.message)
            else:
                log.write_error(sudo_result.message)

            # The xrdp RDP login needs a real password; a freshly created
            # user's password is locked. Prompt rather than leave the
            # user with an account they cannot log into.
            pw_status = await wsl_install.get_password_status(config, username, on_line)
            if pw_status != "P":
                from .password_prompt import PasswordPromptScreen
                password = await self.app.push_screen_wait(PasswordPromptScreen(username))
                if password:
                    pw_result = await wsl_install.set_user_password(config, username, password, on_line)
                    if pw_result.ok:
                        log.write_success(pw_result.message)
                    else:
                        log.write_error(pw_result.message)
                else:
                    log.write_info(
                        f"No password set — RDP login will not work until you run: "
                        f"wsl -d {config.distroImportName} -- sudo passwd {username}"
                    )

            user_result = await wsl_install.set_default_user(config, username, on_line)
            if user_result.skipped:
                tasks.set_status("set_user", "skipped", f"already set to {username}")
            elif user_result.ok:
                tasks.set_status("set_user", "done")
            else:
                tasks.set_status("set_user", "failed")
                log.write_error(user_result.message)
            return True

        async def write_config_step() -> bool:
            log.write_command("Writing .wslconfig...")
            tasks.set_status("write_config", "running")
            wc_result = write_wslconfig(config, overwrite=True)
            tasks.set_status("write_config", "done" if wc_result.ok else "failed")
            if wc_result.ok:
                log.write_success(wc_result.message)
            else:
                log.write_error(wc_result.message)
            return True

        async def wait_ready(require_systemd: bool) -> None:
            log.write_info("Waiting for WSL to become ready...")
            flog.info("Probing WSL readiness (require_systemd=%s)...", require_systemd)
            ready = await wsl_install.wait_for_wsl_ready(
                config, on_line, require_systemd=require_systemd
            )
            if not ready:
                flog.warning("WSL readiness probe timed out, proceeding anyway")
                log.write_info("WSL slow to respond, proceeding...")

        async def shutdown_step() -> bool:
            log.write_command("wsl --shutdown")
            await run_task("shutdown_wsl", wsl_install.shutdown_wsl(on_line))
            # systemd isn't enabled yet at this point — only wait for a shell.
            await wait_ready(require_systemd=False)
            return True

        # Compute script dir for Linux invocation
        script_dir = str(Path(__file__).resolve().parents[3])

        async def on_task_update(task_id: str, task_status: str) -> None:
            log.write_info(f"  [{task_id}] {task_status}")

        def activity_ticker(task_id: str):
            """Show the latest raw output line on the task row (throttled).

            The raw apt/snap stream is far too chatty for the log pane —
            it would scroll all the status history away — so it renders
            as a one-line ticker next to the running task instead.
            """
            state = {"last": 0.0}

            async def on_output(line: str) -> None:
                now = time.monotonic()
                text = line.strip()
                if text and now - state["last"] >= 0.25:
                    state["last"] = now
                    tasks.set_detail(task_id, text[:80])

            return on_output

        async def linux_systemd_step() -> bool:
            log.write_command("Running Linux setup: enable systemd...")
            tasks.set_status("linux_systemd", "running")
            lp1 = await run_linux_headless(config, "enable-systemd", script_dir, on_line,
                                           on_task_update, activity_ticker("linux_systemd"))
            if lp1.success:
                tasks.set_detail("linux_systemd", "")
                tasks.set_status("linux_systemd", "done")
            else:
                tasks.set_status("linux_systemd", "failed")
                log.write_error("Linux enable-systemd failed")
                status.update("[red]Linux setup: enable systemd failed.[/]")
                return False
            return True

        async def restart_step() -> bool:
            log.write_command("Restarting WSL for systemd...")
            await run_task("restart_wsl", wsl_install.shutdown_wsl(on_line))
            await wait_ready(require_systemd=config.enableSystemd)
            return True

        async def linux_packages_step() -> bool:
            log.write_command("Running Linux setup: install packages...")
            tasks.set_status("linux_packages", "running")
            on_output = activity_ticker("linux_packages")
            max_retries = 2
            lp2 = None
            for attempt in range(1, max_retries + 1):
                lp2 = await run_linux_headless(config, "install-packages", script_dir, on_line,
                                               on_task_update, on_output)
                if lp2.success:
                    break
                if attempt < max_retries:
                    flog.warning("Linux install-packages attempt %d failed, retrying...", attempt)
                    log.write_info(f"Install packages attempt {attempt} failed, retrying...")
                    await asyncio.sleep(5)
            if lp2.success:
                tasks.set_detail("linux_packages", "")
                tasks.set_status("linux_packages", "done")
            else:
                tasks.set_status("linux_packages", "failed")
                log.write_error("Linux install-packages failed")
                status.update("[yellow]Linux package installation had issues. Run verification to check.[/]")
            return True

        async def linux_xrdp_step() -> bool:
            log.write_command("Running Linux setup: configure xrdp...")
            tasks.set_status("linux_xrdp", "running")
            lp3 = await run_linux_headless(config, "configure-xrdp", script_dir, on_line,
                                           on_task_update, activity_ticker("linux_xrdp"))
            if lp3.success:
                tasks.set_detail("linux_xrdp", "")
                tasks.set_status("linux_xrdp", "done")
                log.write_success("All tasks complete!")
                status.update("[green]Setup complete! Run verification to confirm.[/]")
            else:
                tasks.set_status("linux_xrdp", "failed")
                log.write_error("Linux configure-xrdp failed")
                status.update("[yellow]xrdp configuration had issues. Run verification to check.[/]")
            return True

        # ── Flow definition ──────────────────────────────────────
        # Each entry is (first task id of the block, step coroutine);
        # the driver applies the resume guard in exactly one place.

        pre_reboot_flow = [
            ("validate_build", validator_step(
                "validate_build", "Checking Windows build...",
                lambda: validators.check_windows_build(on_line),
                "[red]Setup cannot continue. Windows build too old.[/]")),
            ("check_virt", validator_step(
                "check_virt", "Checking virtualization...",
                lambda: validators.check_virtualization(on_line),
                "[red]Enable virtualization in BIOS/UEFI and try again.[/]")),
            ("check_drive", validator_step(
                "check_drive", f"Checking drive {config.wslDriveLetter}:...",
                lambda: validators.check_drive_exists(config.wslDriveLetter, on_line),
                f"[red]Drive {config.wslDriveLetter}: not found.[/]")),
            ("check_wsl", feature_step(
                "check_wsl", "enable_wsl", "Microsoft-Windows-Subsystem-Linux",
                features.enable_wsl_feature, "WSL feature")),
            ("check_vm", feature_step(
                "check_vm", "enable_vm", "VirtualMachinePlatform",
                features.enable_vm_platform, "Virtual Machine Platform")),
        ]

        post_reboot_flow = [
            ("update_wsl", update_wsl_step),
            ("set_version", set_version_step),
            ("install_distro", install_distro_step),
            ("export_distro", export_import_step),
            ("set_user", set_user_step),
            ("write_config", write_config_step),
            ("shutdown_wsl", shutdown_step),
            ("linux_systemd", linux_systemd_step),
            ("restart_wsl", restart_step),
            ("linux_packages", linux_packages_step),
            ("linux_xrdp", linux_xrdp_step),
        ]

        async def drive(flow) -> bool:
            for task_id, step in flow:
                if start_index <= TASK_IDS.index(task_id):
                    if not await step():
                        return False
            return True

        if not await drive(pre_reboot_flow):
            return

        # ── Reboot checkpoint ────────────────────────────────────

        if self._needs_reboot:
            flog.info("=== Reboot required, saving state ===")
            log.write_success("Features enabled. A reboot is required.")
            status.update("[yellow]Reboot required. After reboot, re-run to continue setup.[/]")
            self.query_one("#btn-reboot").remove_class("hidden")
            save_state(SetupState(
                resume_from_task=RESUME_AFTER_REBOOT,
                config_path=str(config.wslInstallPath),
            ))
            return

        if not await drive(post_reboot_flow):
            return

        flog.info("=== Setup finished ===")

        # Clear reboot state
        clear_state()

        # Show verify and launcher buttons
        self.query_one("#btn-verify").remove_class("hidden")
        self.query_one("#btn-launcher").remove_class("hidden")

    def action_reboot(self) -> None:
        btn = self.query_one("#btn-reboot")
        if "hidden" not in btn.classes:
            import subprocess
            subprocess.Popen(["shutdown", "/r", "/t", "5"])
            self.app.exit()

    def action_verify(self) -> None:
        btn = self.query_one("#btn-verify")
        if "hidden" not in btn.classes:
            from .verify import VerifyScreen
            self.app.switch_screen(VerifyScreen(self._config))

    def action_launcher(self) -> None:
        btn = self.query_one("#btn-launcher")
        if "hidden" not in btn.classes:
            from .launcher import LauncherScreen
            self.app.switch_screen(LauncherScreen(self._config))
