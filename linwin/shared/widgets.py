"""Shared TUI widgets: TaskListWidget, LogPanel, VerifyDashboard, AsciiCheckbox, AsciiRadioSet."""

from __future__ import annotations

from rich.markup import escape as rich_escape
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Label, RichLog, Static

from .setup_logging import get_logger


class AsciiCheckbox(Widget):
    """A checkbox using plain ASCII: [X] checked, [ ] unchecked."""

    DEFAULT_CSS = """
    AsciiCheckbox {
        height: 1;
        width: 1fr;
    }
    AsciiCheckbox .checkbox-label {
        width: 1fr;
    }
    """

    value: reactive[bool] = reactive(False)

    class Changed(Message):
        """Posted when the checkbox value changes."""
        def __init__(self, checkbox: "AsciiCheckbox", value: bool) -> None:
            super().__init__()
            self.checkbox = checkbox
            self.value = value

    def __init__(self, label: str, value: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self.value = value

    def _render_text(self) -> str:
        mark = "X" if self.value else " "
        return f"\\[{mark}] {self._label}"

    def compose(self) -> ComposeResult:
        yield Static(self._render_text(), classes="checkbox-label")

    def watch_value(self, new_value: bool) -> None:
        try:
            self.query_one(".checkbox-label", Static).update(self._render_text())
        except Exception:
            pass

    def on_click(self) -> None:
        self.value = not self.value
        self.post_message(self.Changed(self, self.value))


class AsciiRadioSet(Widget):
    """A radio set using plain ASCII: (*) selected, ( ) unselected."""

    DEFAULT_CSS = """
    AsciiRadioSet {
        height: auto;
        width: 1fr;
    }
    AsciiRadioSet .radio-option {
        height: 1;
        width: 1fr;
    }
    """

    pressed_index: reactive[int] = reactive(0)

    class Changed(Message):
        """Posted when the selection changes."""
        def __init__(self, radio_set: "AsciiRadioSet", index: int) -> None:
            super().__init__()
            self.radio_set = radio_set
            self.index = index

    def __init__(self, labels: list[str], default: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        self._labels = labels
        self.pressed_index = default

    def compose(self) -> ComposeResult:
        for i, label in enumerate(self._labels):
            mark = "*" if i == self.pressed_index else " "
            yield Static(f"({mark}) {label}", classes="radio-option", id=f"radio-{i}")

    def watch_pressed_index(self, new_index: int) -> None:
        try:
            for i, label in enumerate(self._labels):
                mark = "*" if i == new_index else " "
                self.query_one(f"#radio-{i}", Static).update(f"({mark}) {label}")
        except Exception:
            pass

    def on_click(self, event) -> None:
        widget = event.widget
        widget_id = getattr(widget, "id", None)
        if widget_id and widget_id.startswith("radio-"):
            idx = int(widget_id.split("-", 1)[1])
            self.pressed_index = idx
            self.post_message(self.Changed(self, idx))



class TaskRow(Widget):
    """A single task row showing name and status text."""

    DEFAULT_CSS = """
    TaskRow {
        height: 1;
        layout: horizontal;
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
        yield Label(self.task_name, classes="task-name")
        yield Label(self.STATUS_TEXT["pending"], classes="task-status")

    def watch_status(self, value: str) -> None:
        get_logger().info("TASK %-25s -> %s", self.task_id, value)
        try:
            status_label = self.query_one(".task-status", Label)
            status_label.update(self.STATUS_TEXT.get(value, value))

            for s in self.STATUS_TEXT:
                status_label.remove_class(f"task-status-{s}")
            status_label.add_class(f"task-status-{value}")
        except Exception:
            pass  # Widget not yet mounted


class TaskListWidget(Widget):
    """A vertical list of task rows with status tracking."""

    DEFAULT_CSS = """
    TaskListWidget {
        height: auto;
        max-height: 50%;
        border: ascii $primary;
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
        border: ascii $secondary;
        height: 1fr;
        min-height: 8;
    }
    LogPanel RichLog {
        height: 1fr;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._plain_lines: list[str] = []

    def compose(self) -> ComposeResult:
        yield RichLog(highlight=False, markup=True, auto_scroll=True, wrap=True)

    @property
    def log(self) -> RichLog:
        return self.query_one(RichLog)

    def get_text(self) -> str:
        """Return the full log content as plain text."""
        return "\n".join(self._plain_lines)

    def write_command(self, cmd: str) -> None:
        get_logger().info("CMD: %s", cmd)
        self._plain_lines.append(f"> {cmd}")
        self.log.write(f"[bold cyan]> {rich_escape(cmd)}[/]")

    def write_stdout(self, line: str) -> None:
        get_logger().debug("OUT: %s", line)
        self._plain_lines.append(line)
        self.log.write(rich_escape(line))

    def write_stderr(self, line: str) -> None:
        get_logger().warning("ERR: %s", line)
        self._plain_lines.append(line)
        self.log.write(f"[red]{rich_escape(line)}[/]")

    def write_info(self, msg: str) -> None:
        get_logger().info("INFO: %s", msg)
        self._plain_lines.append(msg)
        self.log.write(f"[dim]{rich_escape(msg)}[/]")

    def write_success(self, msg: str) -> None:
        get_logger().info("OK: %s", msg)
        self._plain_lines.append(msg)
        self.log.write(f"[green]{rich_escape(msg)}[/]")

    def write_error(self, msg: str) -> None:
        get_logger().error("FAIL: %s", msg)
        self._plain_lines.append(f"ERROR: {msg}")
        self.log.write(f"[bold red]{rich_escape(msg)}[/]")

    def clear(self) -> None:
        self._plain_lines.clear()
        self.log.clear()


class VerifyDashboard(Widget):
    """A DataTable showing verification results with PASS/FAIL/WARN."""

    DEFAULT_CSS = """
    VerifyDashboard {
        height: auto;
        border: ascii $primary;
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
        tag = "WARN" if warn else ("PASS" if passed else "FAIL")
        get_logger().info("VERIFY %-6s %s  %s", tag, name, detail)
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
