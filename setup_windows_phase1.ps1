#Requires -Version 5.1
<#
.SYNOPSIS
    WSL2 Setup - Phase 1: Enable Windows features (pre-reboot).

.DESCRIPTION
    Validates prerequisites (Windows version, virtualization, V: drive),
    enables the WSL and Virtual Machine Platform features, then prompts
    for a reboot. After rebooting, run setup_windows_phase2.ps1.

.NOTES
    Must be run as Administrator. Will self-elevate if not.
#>

$ErrorActionPreference = 'Stop'

# ---------- Self-elevation ----------
if (-not ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()
    ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Requesting Administrator privileges..." -ForegroundColor Yellow
    Start-Process powershell.exe -Verb RunAs -ArgumentList (
        "-ExecutionPolicy Bypass -File `"$PSCommandPath`""
    )
    exit
}

# ---------- Load config ----------
$configPath = Join-Path $PSScriptRoot "config.json"
if (-not (Test-Path $configPath)) {
    Write-Host "[ERROR] config.json not found at $configPath" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
$config = Get-Content $configPath -Raw | ConvertFrom-Json

# ---------- Step 1/3: Validate prerequisites ----------
Write-Host "`n[1/3] Validating prerequisites..." -ForegroundColor Cyan

# Check Windows version (Windows 10 build 19044+ or Windows 11)
$osVersion = [System.Environment]::OSVersion.Version
$buildNumber = $osVersion.Build
if ($buildNumber -lt 19044) {
    Write-Host "[ERROR] Windows 10 build 19044+ or Windows 11 is required (current build: $buildNumber)." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "  Windows build $buildNumber - OK" -ForegroundColor Green

# Check virtualization
$virtEnabled = (Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled
if (-not $virtEnabled) {
    Write-Host "[ERROR] Hardware virtualization is not enabled." -ForegroundColor Red
    Write-Host "  Please enable Intel VT-x or AMD-V in your BIOS/UEFI settings and try again." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "  Hardware virtualization enabled - OK" -ForegroundColor Green

# Check V: drive
$driveLetter = $config.wslDriveLetter
if (-not (Test-Path "${driveLetter}:\")) {
    Write-Host "[ERROR] Drive ${driveLetter}: not found. Please connect or configure your VM drive." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "  Drive ${driveLetter}: found - OK" -ForegroundColor Green

# ---------- Step 2/3: Enable Windows features ----------
Write-Host "`n[2/3] Checking Windows features..." -ForegroundColor Cyan

$wslFeature = Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux
$vmFeature  = Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform

$needsReboot = $false

if ($wslFeature.State -eq 'Enabled' -and $vmFeature.State -eq 'Enabled') {
    Write-Host "  WSL and Virtual Machine Platform are already enabled." -ForegroundColor Green
    Write-Host "  No reboot needed. You can proceed directly to setup_windows_phase2.ps1." -ForegroundColor Green
} else {
    if ($wslFeature.State -ne 'Enabled') {
        Write-Host "  Enabling Windows Subsystem for Linux..." -ForegroundColor Yellow
        dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart | Out-Null
        Write-Host "  WSL feature enabled." -ForegroundColor Green
        $needsReboot = $true
    } else {
        Write-Host "  WSL feature already enabled." -ForegroundColor Green
    }

    if ($vmFeature.State -ne 'Enabled') {
        Write-Host "  Enabling Virtual Machine Platform..." -ForegroundColor Yellow
        dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart | Out-Null
        Write-Host "  Virtual Machine Platform enabled." -ForegroundColor Green
        $needsReboot = $true
    } else {
        Write-Host "  Virtual Machine Platform already enabled." -ForegroundColor Green
    }
}

# ---------- Step 3/3: Reboot prompt ----------
Write-Host "`n[3/3] Next steps" -ForegroundColor Cyan

if ($needsReboot) {
    Write-Host ""
    Write-Host "  A reboot is required to complete feature installation." -ForegroundColor Yellow
    Write-Host "  After rebooting, run setup_windows_phase2.ps1 as Administrator." -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "  Reboot now? (Y/N)"
    if ($response -eq 'Y' -or $response -eq 'y') {
        Write-Host "  Rebooting..." -ForegroundColor Yellow
        Restart-Computer
    } else {
        Write-Host "  Please reboot manually, then run setup_windows_phase2.ps1 as Administrator." -ForegroundColor Yellow
        Read-Host "Press Enter to exit"
    }
} else {
    Write-Host "  Phase 1 complete. No reboot needed." -ForegroundColor Green
    Write-Host "  Run setup_windows_phase2.ps1 as Administrator to continue." -ForegroundColor Green
    Read-Host "Press Enter to exit"
}
