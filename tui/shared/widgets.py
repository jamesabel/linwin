"""Shared TUI widgets: TaskListWidget, LogPanel, VerifyDashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Label, RichLog, Static

from .theme import ICON_DONE, ICON_FAILED, ICON_PENDING, ICON_RUNNING, ICON_SKIPPED


class TaskRow(Widget):
    """A single task row showing icon, name, and status."""

    DEFAULT_CSS = """
    TaskRow {
        height: 1;
        layout: horizontal;
    }
    TaskRow .task-icon {
        width: 3;
    }
    TaskRow .task-name {
        width: 1fr;
    }
    TaskRow .task-status {
        width: 16;
        text-align: right;
    }
    """

    status: reactive[str] = reactive("pending")

    ICONS = {
        "pending": ICON_PENDING,
        "running": ICON_RUNNING,
        "done": ICON_DONE,
        "failed": ICON_FAILED,
        "skipped": ICON_SKIPPED,
    }

    STATUS_TEXT = {
        "pending": "Pending",
        "running": "Running...",
        "done": "Done",
        "failed": "FAILED",
        "skipped": "Skipped",
    }

    def __init__(self, task_id: str, name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.task_id = task_id
        self.task_name = name

    def compose(self) -> ComposeResult:
        yield Label(self.ICONS["pending"], classes="task-icon")
        yield Label(self.task_name, classes="task-name")
        yield Label(self.STATUS_TEXT["pending"], classes="task-status")

    def watch_status(self, value: str) -> None:
        try:
            icon_label = self.query_one(".task-icon", Label)
            status_label = self.query_one(".task-status", Label)
            icon_label.update(self.ICONS.get(value, ICON_PENDING))
            status_label.update(self.STATUS_TEXT.get(value, value))

            # Update icon color class
            for s in self.ICONS:
                icon_label.remove_class(f"task-icon-{s}")
                status_label.remove_class(f"task-status-{s}")
            icon_label.add_class(f"task-icon-{value}")
            status_label.add_class(f"task-status-{value}")
        except Exception:
            pass  # Widget not yet mounted


class TaskListWidget(Widget):
    """A vertical list of task rows with status tracking."""

    DEFAULT_CSS = """
    TaskListWidget {
        height: auto;
        max-height: 50%;
        border: solid $primary;
        padding: 1 1;
    }
    """

    def __init__(self, tasks: list[tuple[str, str]], **kwargs) -> None:
        """tasks: list of (task_id, task_name) tuples."""
        super().__init__(**kwargs)
        self._tasks = tasks

    def compose(self) -> ComposeResult:
        with Vertical():
            for task_id, task_name in self._tasks:
                yield TaskRow(task_id, task_name, id=f"task-{task_id}")

    def set_status(self, task_id: str, status: str) -> None:
        """Update a task's status by its ID."""
        try:
            row = self.query_one(f"#task-{task_id}", TaskRow)
            row.status = status
        except Exception:
            pass

    def set_all_pending(self) -> None:
        for row in self.query(TaskRow):
            row.status = "pending"


class LogPanel(Widget):
    """A bordered log panel wrapping RichLog with convenience methods."""

    DEFAULT_CSS = """
    LogPanel {
        border: solid $secondary;
        height: 1fr;
        min-height: 8;
    }
    LogPanel RichLog {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=True, markup=True, auto_scroll=True, wrap=True)

    @property
    def log(self) -> RichLog:
        return self.query_one(RichLog)

    def write_command(self, cmd: str) -> None:
        self.log.write(f"[bold cyan]> {cmd}[/]")

    def write_stdout(self, line: str) -> None:
        self.log.write(line)

    def write_stderr(self, line: str) -> None:
        self.log.write(f"[red]{line}[/]")

    def write_info(self, msg: str) -> None:
        self.log.write(f"[dim]{msg}[/]")

    def write_success(self, msg: str) -> None:
        self.log.write(f"[green]{msg}[/]")

    def write_error(self, msg: str) -> None:
        self.log.write(f"[bold red]{msg}[/]")

    def clear(self) -> None:
        self.log.clear()


class VerifyDashboard(Widget):
    """A DataTable showing verification results with PASS/FAIL/WARN."""

    DEFAULT_CSS = """
    VerifyDashboard {
        height: auto;
        border: solid $primary;
        padding: 1 1;
    }
    VerifyDashboard DataTable {
        height: auto;
        max-height: 20;
    }
    VerifyDashboard .verify-summary {
        padding: 1 1 0 1;
        text-style: bold;
    }
    """

    def __init__(self, title: str = "Verification Results", **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._passed = 0
        self._failed = 0
        self._warnings = 0

    def compose(self) -> ComposeResult:
        yield Static(f"[bold]{self._title}[/]")
        table = DataTable(zebra_stripes=True)
        table.add_columns("Status", "Check", "Detail")
        yield table
        yield Static("", classes="verify-summary", id="verify-summary")

    def add_check(self, name: str, passed: bool, detail: str = "", warn: bool = False) -> None:
        table = self.query_one(DataTable)
        if warn:
            status = "[yellow]WARN[/]"
            self._warnings += 1
        elif passed:
            status = "[green]PASS[/]"
            self._passed += 1
        else:
            status = "[red]FAIL[/]"
            self._failed += 1
        table.add_row(status, name, detail)
        self._update_summary()

    def _update_summary(self) -> None:
        summary = self.query_one("#verify-summary", Static)
        total = self._passed + self._failed + self._warnings
        summary.update(
            f"[green]{self._passed} passed[/], "
            f"[red]{self._failed} failed[/], "
            f"[yellow]{self._warnings} warnings[/] "
            f"({total} total)"
        )

    @property
    def all_passed(self) -> bool:
        return self._failed == 0
