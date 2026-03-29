"""Shared result types for setup tasks and validation checks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TaskResult:
    """Result of a setup task or validation check.

    Used across Windows and Linux modules for consistent result handling.
    """

    ok: bool
    message: str
    skipped: bool = False
    detail: str = ""
    needs_restart: bool = False
