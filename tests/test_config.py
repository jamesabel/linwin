"""Tests for shared config: dataclasses, pref-backed persistence, validation."""

import json
from pathlib import Path

import pytest

from linwin.shared.config import (
    AppEntry,
    SetupConfig,
    SnapPackage,
    WslConfig,
    load_config,
    save_config,
    validate_config,
    windows_to_wsl_path,
)


class TestSetupConfigFromDict:
    def test_defaults(self):
        config = SetupConfig.from_dict({})
        assert config.distroName == "Ubuntu-22.04"
        assert config.distroImportName == "Ubuntu"
        assert config.wslDriveLetter == "V"
        assert config.enableSystemd is True
        assert config.wslconfig.memory == "16GB"
        assert config.wslconfig.processors == 8

    def test_custom_values(self):
        data = {
            "distroName": "Ubuntu-24.04",
            "distroImportName": "MyUbuntu",
            "wslDriveLetter": "D",
            "wslInstallPath": "D:\\WSL\\Ubuntu",
            "wslconfig": {"memory": "32GB", "processors": 16, "swap": "16GB"},
            "snaps": [{"name": "firefox", "classic": False}],
            "aptPackages": ["git", "curl"],
            "enableSystemd": False,
        }
        config = SetupConfig.from_dict(data)
        assert config.distroName == "Ubuntu-24.04"
        assert config.distroImportName == "MyUbuntu"
        assert config.wslDriveLetter == "D"
        assert config.wslconfig.memory == "32GB"
        assert config.wslconfig.processors == 16
        assert len(config.snaps) == 1
        assert config.snaps[0].name == "firefox"
        assert config.snaps[0].classic is False
        assert config.aptPackages == ["git", "curl"]
        assert config.enableSystemd is False

    def test_partial_wslconfig(self):
        config = SetupConfig.from_dict({"wslconfig": {"memory": "4GB"}})
        assert config.wslconfig.memory == "4GB"
        assert config.wslconfig.processors == 8  # default preserved

    def test_empty_snaps(self):
        config = SetupConfig.from_dict({"snaps": []})
        assert config.snaps == []


class TestSetupConfigRoundTrip:
    def test_to_dict_and_back(self):
        original = SetupConfig(
            distroName="Test",
            wslDriveLetter="Z",
            optionalApps=[AppEntry("vim", "Vim", "vim", "snap", classic=False)],
        )
        data = original.to_dict()
        restored = SetupConfig.from_dict(data)
        assert restored.distroName == original.distroName
        assert restored.wslDriveLetter == original.wslDriveLetter
        assert len(restored.optionalApps) == 1
        assert restored.optionalApps[0].id == "vim"
        assert restored.snaps[0].name == "vim"
        assert restored.snaps[0].classic is False


class TestValidateConfig:
    def test_valid_config(self):
        config = SetupConfig()
        assert validate_config(config) == []

    def test_empty_distro_name(self):
        config = SetupConfig(distroName="")
        errors = validate_config(config)
        assert any("distroName" in e for e in errors)

    def test_empty_import_name(self):
        config = SetupConfig(distroImportName="")
        errors = validate_config(config)
        assert any("distroImportName" in e for e in errors)

    def test_bad_drive_letter(self):
        config = SetupConfig(wslDriveLetter="AB")
        errors = validate_config(config)
        assert any("wslDriveLetter" in e for e in errors)

    def test_empty_drive_letter(self):
        config = SetupConfig(wslDriveLetter="")
        errors = validate_config(config)
        assert any("wslDriveLetter" in e for e in errors)

    def test_empty_install_path(self):
        config = SetupConfig(wslInstallPath="")
        errors = validate_config(config)
        assert any("wslInstallPath" in e for e in errors)

    def test_zero_processors(self):
        config = SetupConfig(wslconfig=WslConfig(processors=0))
        errors = validate_config(config)
        assert any("processors" in e for e in errors)

    def test_multiple_errors(self):
        config = SetupConfig(distroName="", wslDriveLetter="", wslInstallPath="")
        errors = validate_config(config)
        assert len(errors) >= 3


class TestPrefPersistence:
    """Test sqlite-backed load/save with injected db_path."""

    def test_save_and_reload(self, tmp_path):
        db = tmp_path / "test.db"
        config = SetupConfig(distroName="SaveTest", wslDriveLetter="X")
        save_config(config, db)

        loaded = load_config(db)
        assert loaded.distroName == "SaveTest"
        assert loaded.wslDriveLetter == "X"

    def test_defaults_on_empty_db(self, tmp_path):
        db = tmp_path / "empty.db"
        config = load_config(db)
        assert config.distroName == "Ubuntu-22.04"
        assert config.enableSystemd is True

    def test_round_trip_complex_fields(self, tmp_path):
        db = tmp_path / "complex.db"
        config = SetupConfig(
            wslconfig=WslConfig(memory="32GB", processors=16),
            optionalApps=[AppEntry("code", "VS Code", "code", "snap", True)],
            aptPackages=["nautilus", "xfce4"],
        )
        save_config(config, db)

        loaded = load_config(db)
        assert loaded.wslconfig.memory == "32GB"
        assert loaded.wslconfig.processors == 16
        assert len(loaded.optionalApps) == 1
        assert loaded.optionalApps[0].id == "code"
        assert loaded.aptPackages == ["nautilus", "xfce4"]
        assert loaded.snaps[0].name == "code"

    def test_empty_db_gets_defaults(self, tmp_path):
        """An empty DB should be initialized with defaults."""
        db = tmp_path / "fresh.db"
        config = load_config(db)
        assert config.distroName == "Ubuntu-22.04"
        assert config.enableSystemd is True
        # Loading again should return the persisted defaults.
        config2 = load_config(db)
        assert config2.distroName == "Ubuntu-22.04"


class TestWindowsToWslPath:
    def test_c_drive(self):
        assert windows_to_wsl_path("C:\\Users\\test") == "/mnt/c/Users/test"

    def test_v_drive(self):
        assert windows_to_wsl_path("V:\\WSL\\Ubuntu") == "/mnt/v/WSL/Ubuntu"

    def test_lowercase_drive(self):
        result = windows_to_wsl_path("d:\\data")
        assert result == "/mnt/d/data"

    def test_uppercase_drive_lowered(self):
        result = windows_to_wsl_path("D:\\data")
        assert result == "/mnt/d/data"

    def test_no_drive_letter(self):
        assert windows_to_wsl_path("/some/path") == "/some/path"

    def test_nested_path(self):
        result = windows_to_wsl_path("C:\\a\\b\\c\\d")
        assert result == "/mnt/c/a/b/c/d"
