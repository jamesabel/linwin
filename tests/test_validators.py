"""Tests for the validators module data structures and parsing logic."""

from linwin.shared.task_result import TaskResult


class TestTaskResult:
    def test_ok_result(self):
        r = TaskResult(ok=True, message="All good")
        assert r.ok is True
        assert r.message == "All good"
        assert r.detail == ""

    def test_failed_result_with_detail(self):
        r = TaskResult(ok=False, message="Failed", detail="Do X to fix")
        assert r.ok is False
        assert r.detail == "Do X to fix"

    def test_skipped_result(self):
        r = TaskResult(ok=True, message="Already done", skipped=True)
        assert r.skipped is True

    def test_needs_restart(self):
        r = TaskResult(ok=True, message="Enabled", needs_restart=True)
        assert r.needs_restart is True

    def test_defaults(self):
        r = TaskResult(ok=True, message="OK")
        assert r.skipped is False
        assert r.detail == ""
        assert r.needs_restart is False
