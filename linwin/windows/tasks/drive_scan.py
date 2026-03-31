"""Scan system drives and rank candidates for WSL2 storage."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...shared.subprocess_runner import LineCallback, run_powershell

MIN_FREE_GB = 20.0


@dataclass
class DriveCandidate:
    """A fixed drive on the system, ranked as a candidate for WSL storage."""

    letter: str
    free_gb: float
    total_gb: float
    media_type: str  # "SSD", "HDD", "Unspecified", "Unknown"
    bus_type: str  # "NVMe", "SATA", "USB", "RAID", etc.
    label: str
    score: int = 0

    @property
    def type_display(self) -> str:
        if self.bus_type == "NVMe":
            return "NVMe SSD"
        if self.media_type == "SSD":
            return "SSD"
        if self.media_type == "HDD":
            return "HDD"
        return self.media_type


@dataclass
class DriveScanResult:
    """Result of a system drive scan with ranked candidates and excluded drives."""

    candidates: list[DriveCandidate] = field(default_factory=list)
    excluded: list[tuple[str, str]] = field(default_factory=list)
    error: str = ""


def score_drive(d: DriveCandidate) -> int:
    """Score a drive candidate for WSL storage suitability. Higher is better.

    Prefers NVMe > SSD > HDD, more free space, and non-system (non-C:) drives.
    """
    score = 0
    # Media type: NVMe > SSD > HDD > Unknown
    if d.bus_type == "NVMe":
        score += 300
    elif d.media_type == "SSD":
        score += 200
    elif d.media_type == "HDD":
        score += 100
    # Free space (1 point per GB, capped)
    score += min(int(d.free_gb), 500)
    # Prefer non-system drive
    if d.letter.upper() != "C":
        score += 50
    return score


def parse_drive_line(line: str) -> DriveCandidate | None:
    """Parse one pipe-delimited line from the PowerShell drive scan.

    Expected format: ``letter|free_gb|total_gb|media_type|bus_type|label``.
    Returns None if the line cannot be parsed.
    """
    parts = line.strip().split("|")
    if len(parts) < 6:
        return None
    try:
        return DriveCandidate(
            letter=parts[0].strip(),
            free_gb=float(parts[1]),
            total_gb=float(parts[2]),
            media_type=parts[3].strip() or "Unknown",
            bus_type=parts[4].strip() or "Unknown",
            label=parts[5].strip(),
        )
    except (ValueError, IndexError):
        return None


_SCAN_SCRIPT = """
$vols = Get-Volume | Where-Object { $_.DriveLetter -and $_.DriveType -eq 'Fixed' -and $_.Size -gt 0 }
foreach ($v in $vols) {
    $letter = $v.DriveLetter
    $mediaType = 'Unknown'
    $busType = 'Unknown'
    try {
        $part = Get-Partition -DriveLetter $letter -ErrorAction SilentlyContinue
        if ($part) {
            $disk = Get-Disk -Number $part.DiskNumber -ErrorAction SilentlyContinue
            if ($disk) {
                $pd = Get-PhysicalDisk | Where-Object { $_.DeviceId -eq [string]$disk.Number }
                if ($pd) {
                    $mediaType = $pd.MediaType
                    $busType = $pd.BusType
                }
            }
        }
    } catch {}
    $freeGB = [math]::Round($v.SizeRemaining / 1GB, 1)
    $totalGB = [math]::Round($v.Size / 1GB, 1)
    $label = if ($v.FileSystemLabel) { $v.FileSystemLabel } else { '' }
    Write-Output "$letter|$freeGB|$totalGB|$mediaType|$busType|$label"
}
""".strip()


async def scan_drives(on_line: LineCallback | None = None) -> DriveScanResult:
    """Scan system drives and return ranked candidates for WSL storage."""
    result = await run_powershell(_SCAN_SCRIPT, on_line=on_line)
    if not result.success:
        return DriveScanResult(error="Failed to scan drives")

    candidates: list[DriveCandidate] = []
    excluded: list[tuple[str, str]] = []

    for line in result.output.strip().splitlines():
        drive = parse_drive_line(line)
        if drive is None:
            continue
        # Filter: USB-attached drives
        if drive.bus_type == "USB":
            excluded.append((drive.letter, "USB external drive"))
            continue
        # Filter: insufficient free space
        if drive.free_gb < MIN_FREE_GB:
            excluded.append((drive.letter, f"Only {drive.free_gb} GB free"))
            continue
        drive.score = score_drive(drive)
        candidates.append(drive)

    candidates.sort(key=lambda d: d.score, reverse=True)
    return DriveScanResult(candidates=candidates, excluded=excluded)
