"""Modal prompt for setting the Linux user's password.

Shown during setup when the default user's password is locked or unset
(a freshly created user has a locked password), because the xrdp RDP
login requires a real password.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class PasswordPromptScreen(ModalScreen[str | None]):
    """Ask for a password for the Linux user.

    Dismisses with the password string, or None when skipped.
    """

    BINDINGS = [
        ("escape", "skip", "Skip"),
    ]

    CSS = """
    PasswordPromptScreen {
        align: center middle;
    }
    #pw-dialog {
        border: ascii $primary;
        background: $surface;
        width: 64;
        height: auto;
        padding: 1 2;
    }
    #pw-title {
        text-style: bold;
        color: $primary;
        margin-bottom: 1;
    }
    #pw-error {
        color: $warning;
    }
    """

    def __init__(self, username: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._username = username

    def compose(self) -> ComposeResult:
        with Vertical(id="pw-dialog"):
            yield Static(f"Set a password for Linux user '{self._username}'", id="pw-title")
            yield Static("This password is used for the Remote Desktop (xrdp) login.")
            yield Input(placeholder="Password", password=True, id="pw-input")
            yield Input(placeholder="Confirm password", password=True, id="pw-confirm")
            yield Static("", id="pw-error")
            yield Static("[dim]\\[Enter] Save   \\[Esc] Skip (set later with: sudo passwd)[/]")

    def on_mount(self) -> None:
        self.query_one("#pw-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "pw-input":
            self.query_one("#pw-confirm", Input).focus()
        else:
            self.action_submit()

    def action_submit(self) -> None:
        password = self.query_one("#pw-input", Input).value
        confirm = self.query_one("#pw-confirm", Input).value
        error = self.query_one("#pw-error", Static)
        if not password:
            error.update("Password cannot be empty.")
            return
        if password != confirm:
            error.update("Passwords do not match.")
            return
        self.dismiss(password)

    def action_skip(self) -> None:
        self.dismiss(None)
