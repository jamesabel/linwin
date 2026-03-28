"""Tests for shared config loading, parsing, validation, and serialization."""

import json
import os
from pathlib import Path

import pytest

from tui.shared.config import (
    SetupConfig,
    SnapPackage,
    WslConfig,
    get_config_path,
    load_config,
    save_config,
    validate_config,
    windows_to_wsl_path,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_JSON = PROJECT_ROOT / "config.json"


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
            snaps=[SnapPackage("vim", False)],
        )
        data = original.to_dict()
        restored = SetupConfig.from_dict(data)
        assert restored.distroName == original.distroName
        assert restored.wslDriveLetter == original.wslDriveLetter
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


class TestLoadConfig:
    def test_load_project_config(self):
        config = load_config(CONFIG_JSON)
        assert config.distroName == "Ubuntu-22.04"
        assert len(config.snaps) == 2
        assert config.snaps[0].name == "intellij-idea-community"

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_config(tmp_path / "nonexistent.json")


class TestSaveConfig:
    def test_save_and_reload(self, tmp_path):
        config = SetupConfig(distroName="SaveTest", wslDriveLetter="X")
        path = tmp_path / "config.json"
        save_config(config, path)

        loaded = load_config(path)
        assert loaded.distroName == "SaveTest"
        assert loaded.wslDriveLetter == "X"

    def test_saved_json_is_valid(self, tmp_path):
        config = SetupConfig()
        path = tmp_path / "config.json"
        save_config(config, path)

        data = json.loads(path.read_text())
        assert "distroName" in data
        assert "wslconfig" in data


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
