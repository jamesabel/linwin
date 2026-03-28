#Requires -Version 5.1
<#
.SYNOPSIS
    Verify WSL2 + Ubuntu + WSLg setup.

.DESCRIPTION
    Checks all components of the setup: Windows features, WSL version,
    distro registration, V: drive location, .wslconfig, and invokes
    _verify_setup.sh inside WSL for Linux-side checks.
#>

$ErrorActionPreference = 'Stop'

# ---------- Load config ----------
$configPath = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path $configPath)) {
    Write-Host "[ERROR] config.json not found at $configPath" -ForegroundColor Red
    exit 1
}
$config = Get-Content $configPath -Raw | ConvertFrom-Json

$distroImportName = $config.distroImportName
$installPath      = $config.wslInstallPath
$driveLetter      = $config.wslDriveLetter

$passed = 0
$failed = 0
$warnings = 0

function Test-Check {
    param([string]$Name, [bool]$Result, [string]$Detail = "")
    if ($Result) {
        Write-Host "  [PASS] $Name" -ForegroundColor Green
        if ($Detail) { Write-Host "         $Detail" -ForegroundColor Gray }
        $script:passed++
    } else {
        Write-Host "  [FAIL] $Name" -ForegroundColor Red
        if ($Detail) { Write-Host "         $Detail" -ForegroundColor Gray }
        $script:failed++
    }
}

function Test-Warn {
    param([string]$Name, [string]$Detail = "")
    Write-Host "  [WARN] $Name" -ForegroundColor Yellow
    if ($Detail) { Write-Host "         $Detail" -ForegroundColor Gray }
    $script:warnings++
}

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  WSL2 Setup Verification" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# ---------- Windows Features ----------
Write-Host "Windows Features:" -ForegroundColor White

$wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
Test-Check "WSL feature enabled" ($wslFeature.State -eq 'Enabled')

$vmFeature = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform
Test-Check "Virtual Machine Platform enabled" ($vmFeature.State -eq 'Enabled')

# ---------- WSL Installation ----------
Write-Host "`nWSL Installation:" -ForegroundColor White

try {
    $wslVersion = wsl --version 2>&1
    Test-Check "WSL installed" $true ($wslVersion | Select-Object -First 1)
} catch {
    Test-Check "WSL installed" $false "wsl --version failed"
}

# ---------- Distro ----------
Write-Host "`nDistro:" -ForegroundColor White

$registeredDistros = wsl -l -q 2>$null | ForEach-Object { ($_ -replace "`0", "").Trim() } | Where-Object { $_ }
$distroRegistered = $registeredDistros -contains $distroImportName
Test-Check "Distro '$distroImportName' registered" $distroRegistered

if ($distroRegistered) {
    # Check version is 2
    $distroInfo = wsl -l -v 2>$null | ForEach-Object { ($_ -replace "`0", "").Trim() } | Where-Object { $_ -match $distroImportName }
    $isVersion2 = $distroInfo -match "2"
    Test-Check "Distro is WSL version 2" $isVersion2 $distroInfo
}

# ---------- V: Drive ----------
Write-Host "`nStorage:" -ForegroundColor White

Test-Check "Drive ${driveLetter}: exists" (Test-Path "${driveLetter}:\")

$vhdPath = Join-Path $installPath "ext4.vhdx"
Test-Check "Distro VHD on ${driveLetter}: drive" (Test-Path $vhdPath) $vhdPath

# ---------- .wslconfig ----------
Write-Host "`nConfiguration:" -ForegroundColor White

$wslconfigPath = Join-Path $env:USERPROFILE ".wslconfig"
Test-Check ".wslconfig exists" (Test-Path $wslconfigPath) $wslconfigPath

if (Test-Path $wslconfigPath) {
    $wslconfigContent = Get-Content $wslconfigPath -Raw
    Test-Check ".wslconfig has guiApplications=true" ($wslconfigContent -match "guiApplications\s*=\s*true")
}

# ---------- Linux-side checks ----------
Write-Host "`nLinux-side checks:" -ForegroundColor White

if ($distroRegistered) {
    # Compute WSL path for script directory
    $winPath = $PSScriptRoot
    $wslPath = $winPath -replace '\\', '/'
    if ($wslPath -match '^([A-Za-z]):(.*)') {
        $wslPath = "/mnt/$($Matches[1].ToLower())$($Matches[2])"
    }

    try {
        $linuxResult = wsl -d $distroImportName -- bash -c "cd '$wslPath' && bash _verify_setup.sh 2>&1"
        $linuxResult | ForEach-Object { Write-Host $_ }
    } catch {
        Test-Check "Linux-side verification" $false "Failed to run _verify_setup.sh"
    }
} else {
    Test-Warn "Skipping Linux-side checks" "Distro not registered"
}

# ---------- Summary ----------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Results: $passed passed, $failed failed, $warnings warnings" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

if ($failed -gt 0) {
    Write-Host "Some checks failed. Review the output above." -ForegroundColor Red
    exit 1
} else {
    Write-Host "All Windows-side checks passed!" -ForegroundColor Green
}

Read-Host "Press Enter to exit"
