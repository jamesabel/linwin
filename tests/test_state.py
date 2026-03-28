"""Tests for setup state persistence."""

import json
import os
from unittest.mock import patch

import pytest

from tui.windows.tasks.state import SetupState, clear_state, load_state, save_state


@pytest.fixture
def state_dir(tmp_path):
    """Redirect state storage to a temp directory."""
    with patch("tui.windows.tasks.state._state_dir", return_value=tmp_path):
        yield tmp_path


class TestSaveAndLoadState:
    def test_round_trip(self, state_dir):
        state = SetupState(phase1_complete=True, needs_reboot=True, config_path="V:\\WSL")
        save_state(state)
        loaded = load_state()
        assert loaded is not None
        assert loaded.phase1_complete is True
        assert loaded.needs_reboot is True
        assert loaded.config_path == "V:\\WSL"
        assert loaded.timestamp != ""

    def test_load_returns_none_when_no_file(self, state_dir):
        assert load_state() is None

    def test_clear_state(self, state_dir):
        save_state(SetupState(phase1_complete=True))
        clear_state()
        assert load_state() is None

    def test_clear_when_no_file(self, state_dir):
        # Should not raise
        clear_state()

    def test_corrupted_json_returns_none(self, state_dir):
        state_file = state_dir / "setup_state.json"
        state_file.write_text("not valid json{{{")
        assert load_state() is None

    def test_save_creates_directory(self, tmp_path):
        nested = tmp_path / "sub" / "dir"
        with patch("tui.windows.tasks.state._state_dir", return_value=nested):
            save_state(SetupState(phase2_complete=True))
            loaded = load_state()
            assert loaded is not None
            assert loaded.phase2_complete is True


class TestSetupStateDefaults:
    def test_defaults(self):
        state = SetupState()
        assert state.phase1_complete is False
        assert state.needs_reboot is False
        assert state.phase2_complete is False
        assert state.config_path == ""
        assert state.timestamp == ""
