"""Linux TUI Setup Screen — systemd, apt, snap, WSLg verification."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from ...shared.base_app import ClickDispatchScreen
from textual.widgets import Static
from textual import work

from ...shared.config import SetupConfig
from ...shared.widgets import LogPanel, TaskListWidget
from ..tasks.steps import build_package_steps, run_steps


def build_task_list(config: SetupConfig) -> list[tuple[str, str]]:
    """Build the task list from the shared step sequence.

    Returns a list of ``(task_id, display_name)`` tuples reflecting
    the packages and options enabled in the current configuration.
    """
    return [(s.task_id, s.label) for s in build_package_steps(config)]


class TuiReporter:
    """StepReporter that renders to the TaskListWidget and LogPanel."""

    def __init__(self, tasks: TaskListWidget, log: LogPanel) -> None:
        self._tasks = tasks
        self._log = log

    def set_status(self, task_id: str, status: str) -> None:
        self._tasks.set_status(task_id, status)

    def command(self, msg: str) -> None:
        self._log.write_command(msg)

    def info(self, msg: str) -> None:
        self._log.write_info(msg)

    def error(self, msg: str) -> None:
        self._log.write_error(msg)


class SetupScreen(ClickDispatchScreen):
    """Run all Linux setup tasks with live progress."""

    BINDINGS = [
        ("1", "run_verify", "Verify"),
    ]

    CLICK_MAP = {
        "btn-verify": "run_verify",
    }

    CSS = """
    #setup-status {
        padding: 1 2;
        text-style: bold;
    }
    #btn-verify {
        color: $success;
    }
    """

    def __init__(self, config: SetupConfig, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config

    def compose(self) -> ComposeResult:
        task_list = build_task_list(self._config)
        with VerticalScroll():
            yield TaskListWidget(task_list, id="setup-tasks")
            yield LogPanel(id="setup-log")
            yield Static("", id="setup-status")
            with Horizontal(classes="button-bar"):
                yield Static("\\[1] Run Verification", id="btn-verify", classes="action-link hidden")

    def on_mount(self) -> None:
        self.run_setup()

    @work(exclusive=True)
    async def run_setup(self) -> None:
        tasks = self.query_one("#setup-tasks", TaskListWidget)
        log = self.query_one("#setup-log", LogPanel)
        status = self.query_one("#setup-status", Static)

        reporter = TuiReporter(tasks, log)
        steps = build_package_steps(self._config)
        await run_steps(steps, reporter, on_line=log.as_line_callback)

        # Summary
        log.write_success("\nSetup complete!")
        status.update("[green]Setup complete! Run verification to confirm.[/]")
        self.query_one("#btn-verify").remove_class("hidden")

    def action_run_verify(self) -> None:
        from .verify import VerifyScreen
        self.app.switch_screen(VerifyScreen(self._config))
