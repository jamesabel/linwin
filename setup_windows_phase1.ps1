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

# Check virtualization — gather full diagnostic info
$cpu = Get-CimInstance Win32_Processor
$virtEnabled = $cpu.VirtualizationFirmwareEnabled
$cpuName = $cpu.Name
$cpuMfr = $cpu.Manufacturer
$hypervisorPresent = (Get-CimInstance Win32_ComputerSystem).HypervisorPresent
$wslState = (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Windows-Subsystem-Linux -ErrorAction SilentlyContinue).State
$vmState = (Get-WindowsOptionalFeature -Online -FeatureName VirtualMachinePlatform -ErrorAction SilentlyContinue).State
$hvState = (Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All -ErrorAction SilentlyContinue).State

if (-not $virtEnabled) {
    $isIntel = $cpuMfr -match "Intel|GenuineIntel"
    if ($isIntel) {
        $biosTech = "Intel VT-x"
        $biosMenuHint = "look under Advanced > CPU Configuration or Security > Virtualization Technology"
    } else {
        $biosTech = "AMD-V (SVM)"
        $biosMenuHint = "look under Advanced > CPU Configuration or M.I.T. > SVM Mode"
    }

    Write-Host ""
    Write-Host "[ERROR] Hardware virtualization is not enabled." -ForegroundColor Red
    Write-Host ""
    Write-Host "  Virtualization diagnostic:" -ForegroundColor Yellow
    Write-Host "    Processor:                $cpuName"
    Write-Host "    BIOS virtualization:      DISABLED  <-- action needed" -ForegroundColor Red
    Write-Host "    Hypervisor running:       $(if ($hypervisorPresent) {'Yes'} else {'No'})"
    Write-Host "    WSL feature:              $wslState"
    Write-Host "    Virtual Machine Platform: $vmState"
    Write-Host "    Hyper-V:                  $hvState"
    Write-Host ""
    Write-Host "  Your processor supports $biosTech but it is turned off in BIOS/UEFI." -ForegroundColor Yellow
    Write-Host "  To fix this:" -ForegroundColor Yellow
    Write-Host "    1. Restart your PC and enter BIOS/UEFI setup (usually DEL, F2, or F10 at boot)" -ForegroundColor Yellow
    Write-Host "    2. In the BIOS menus, $biosMenuHint" -ForegroundColor Yellow
    Write-Host "    3. Set $biosTech to Enabled" -ForegroundColor Yellow
    Write-Host "    4. Save and exit (usually F10)" -ForegroundColor Yellow
    Write-Host "    5. Re-run this setup after Windows boots" -ForegroundColor Yellow
    Write-Host ""
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
