"""Tests for the validators module data structures and parsing logic."""

from tui.windows.tasks.validators import ValidationResult


class TestValidationResult:
    def test_ok_result(self):
        r = ValidationResult(ok=True, message="All good")
        assert r.ok is True
        assert r.message == "All good"
        assert r.detail == ""

    def test_failed_result_with_detail(self):
        r = ValidationResult(ok=False, message="Failed", detail="Do X to fix")
        assert r.ok is False
        assert r.detail == "Do X to fix"
