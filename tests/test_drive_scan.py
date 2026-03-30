"""Tests for drive scanning and ranking logic."""

import pytest

from linwin.windows.tasks.drive_scan import (
    DriveCandidate,
    DriveScanResult,
    parse_drive_line,
    score_drive,
)


class TestParseDriverLine:
    def test_valid_line(self):
        d = parse_drive_line("C|150.3|500.0|SSD|SATA|Windows")
        assert d is not None
        assert d.letter == "C"
        assert d.free_gb == 150.3
        assert d.total_gb == 500.0
        assert d.media_type == "SSD"
        assert d.bus_type == "SATA"
        assert d.label == "Windows"

    def test_empty_label(self):
        d = parse_drive_line("D|200.0|1000.0|HDD|SATA|")
        assert d is not None
        assert d.label == ""

    def test_nvme(self):
        d = parse_drive_line("E|400.0|1000.0|SSD|NVMe|Fast Drive")
        assert d is not None
        assert d.bus_type == "NVMe"

    def test_too_few_fields(self):
        assert parse_drive_line("C|150") is None

    def test_empty_string(self):
        assert parse_drive_line("") is None

    def test_bad_number(self):
        assert parse_drive_line("C|abc|500.0|SSD|SATA|Windows") is None

    def test_pipe_in_label(self):
        d = parse_drive_line("C|150.3|500.0|SSD|SATA|My|Drive")
        assert d is not None
        # Extra pipe means label is just the 6th field
        assert d.letter == "C"


class TestScoreDrive:
    def test_nvme_beats_ssd(self):
        nvme = DriveCandidate("D", 100, 500, "SSD", "NVMe", "")
        ssd = DriveCandidate("E", 100, 500, "SSD", "SATA", "")
        assert score_drive(nvme) > score_drive(ssd)

    def test_ssd_beats_hdd(self):
        ssd = DriveCandidate("D", 100, 500, "SSD", "SATA", "")
        hdd = DriveCandidate("E", 100, 500, "HDD", "SATA", "")
        assert score_drive(ssd) > score_drive(hdd)

    def test_hdd_beats_unknown(self):
        hdd = DriveCandidate("D", 100, 500, "HDD", "SATA", "")
        unk = DriveCandidate("E", 100, 500, "Unspecified", "SATA", "")
        assert score_drive(hdd) > score_drive(unk)

    def test_more_space_wins_tiebreaker(self):
        big = DriveCandidate("D", 300, 500, "SSD", "SATA", "")
        small = DriveCandidate("E", 100, 500, "SSD", "SATA", "")
        assert score_drive(big) > score_drive(small)

    def test_non_c_drive_preferred(self):
        c = DriveCandidate("C", 100, 500, "SSD", "SATA", "")
        d = DriveCandidate("D", 100, 500, "SSD", "SATA", "")
        assert score_drive(d) > score_drive(c)

    def test_space_capped(self):
        huge = DriveCandidate("D", 10000, 20000, "SSD", "SATA", "")
        big = DriveCandidate("E", 500, 1000, "SSD", "SATA", "")
        # Both should have capped space score of 500
        assert score_drive(huge) == score_drive(big)


class TestDriveCandidate:
    def test_type_display_nvme(self):
        d = DriveCandidate("D", 100, 500, "SSD", "NVMe", "")
        assert d.type_display == "NVMe SSD"

    def test_type_display_ssd(self):
        d = DriveCandidate("D", 100, 500, "SSD", "SATA", "")
        assert d.type_display == "SSD"

    def test_type_display_hdd(self):
        d = DriveCandidate("D", 100, 500, "HDD", "SATA", "")
        assert d.type_display == "HDD"

    def test_type_display_unknown(self):
        d = DriveCandidate("D", 100, 500, "Unspecified", "SATA", "")
        assert d.type_display == "Unspecified"


class TestDriveScanResult:
    def test_empty(self):
        r = DriveScanResult()
        assert r.candidates == []
        assert r.excluded == []
        assert r.error == ""

    def test_with_error(self):
        r = DriveScanResult(error="Failed")
        assert r.error == "Failed"
