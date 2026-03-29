"""Tests for the features module data structures."""

from tui.windows.tasks.features import FeatureResult


class TestFeatureResult:
    def test_already_enabled(self):
        r = FeatureResult(already_enabled=True, enabled_now=False)
        assert r.ok is True

    def test_just_enabled(self):
        r = FeatureResult(already_enabled=False, enabled_now=True)
        assert r.ok is True

    def test_failed(self):
        r = FeatureResult(already_enabled=False, enabled_now=False, error="DISM failed")
        assert r.ok is False
        assert r.error == "DISM failed"

    def test_not_needed_no_error(self):
        r = FeatureResult(already_enabled=True, enabled_now=False)
        assert r.error == ""
