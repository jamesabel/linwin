#Requires -Version 5.1
<#
.SYNOPSIS
    WSL2 Setup - Phase 2: Install Ubuntu, move to V:, configure, and run Linux setup.

.DESCRIPTION
    Run this after rebooting from Phase 1. Installs/updates WSL2, installs Ubuntu,
    moves the distro to the V: drive, writes .wslconfig, then invokes _setup_ubuntu.sh
    inside WSL to install packages and verify WSLg.

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

$distroName       = $config.distroName
$distroImportName = $config.distroImportName
$installPath      = $config.wslInstallPath
$driveLetter      = $config.wslDriveLetter

# ---------- Step 1/8: Validate V: drive ----------
Write-Host "`n[1/8] Validating drive ${driveLetter}:..." -ForegroundColor Cyan
if (-not (Test-Path "${driveLetter}:\")) {
    Write-Host "[ERROR] Drive ${driveLetter}: not found." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Host "  Drive ${driveLetter}: found - OK" -ForegroundColor Green

# ---------- Step 2/8: Update WSL ----------
Write-Host "`n[2/8] Updating WSL..." -ForegroundColor Cyan
wsl --update
wsl --set-default-version 2
Write-Host "  WSL updated and default version set to 2." -ForegroundColor Green

# ---------- Step 3/8: Install Ubuntu ----------
Write-Host "`n[3/8] Installing Ubuntu..." -ForegroundColor Cyan

# Check if distro is already registered
$registeredDistros = wsl -l -q 2>$null | Where-Object { $_ -and $_.Trim() }
# Clean up null characters from wsl output
$registeredDistros = $registeredDistros | ForEach-Object { $_ -replace "`0", "" } | Where-Object { $_.Trim() }

$distroExists = $false
foreach ($d in $registeredDistros) {
    if ($d.Trim() -eq $distroImportName -or $d.Trim() -eq $distroName) {
        $distroExists = $true
        break
    }
}

if ($distroExists) {
    Write-Host "  Distro '$distroImportName' is already registered." -ForegroundColor Green
} else {
    Write-Host "  Installing $distroName..." -ForegroundColor Yellow
    Write-Host "  An Ubuntu window will open for initial setup." -ForegroundColor Yellow
    Write-Host "  Please create your UNIX username and password, then type 'exit' to return here." -ForegroundColor Yellow
    Write-Host ""
    Read-Host "  Press Enter to begin the Ubuntu installation"
    wsl --install -d $distroName
    Write-Host ""
    Write-Host "  Ubuntu installed." -ForegroundColor Green
}

# ---------- Step 4/8: Move distro to V: drive ----------
Write-Host "`n[4/8] Moving distro to ${driveLetter}: drive..." -ForegroundColor Cyan

# Determine which name the distro is registered under
$registeredDistros = wsl -l -q 2>$null | ForEach-Object { ($_ -replace "`0", "").Trim() } | Where-Object { $_ }
$currentName = $null
foreach ($d in $registeredDistros) {
    if ($d -eq $distroImportName) { $currentName = $d; break }
    if ($d -eq $distroName)       { $currentName = $d; break }
}

if (-not $currentName) {
    Write-Host "[ERROR] Could not find registered distro '$distroImportName' or '$distroName'." -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if already on V: drive by looking for the VHD
$vhdPath = Join-Path $installPath "ext4.vhdx"
if (Test-Path $vhdPath) {
    Write-Host "  Distro is already located on ${driveLetter}: drive." -ForegroundColor Green
} else {
    Write-Host "  Exporting distro '$currentName'..." -ForegroundColor Yellow
    $exportPath = Join-Path $env:TEMP "wsl_ubuntu_export.tar"
    wsl --export $currentName $exportPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Export failed." -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    Write-Host "  Unregistering distro '$currentName'..." -ForegroundColor Yellow
    wsl --unregister $currentName

    Write-Host "  Importing distro to $installPath..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $installPath | Out-Null
    wsl --import $distroImportName $installPath $exportPath --version 2
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[ERROR] Import failed. The export file is at: $exportPath" -ForegroundColor Red
        Read-Host "Press Enter to exit"
        exit 1
    }

    Remove-Item $exportPath -Force -ErrorAction SilentlyContinue
    Write-Host "  Distro moved to $installPath." -ForegroundColor Green
}

# ---------- Step 5/8: Set default user ----------
Write-Host "`n[5/8] Setting default user..." -ForegroundColor Cyan

# Detect the non-root user created during first boot
$homeUsers = wsl -d $distroImportName -- bash -c "ls /home/ 2>/dev/null" 2>$null
$homeUsers = ($homeUsers -replace "`0", "").Trim()
if ($homeUsers) {
    # Take the first user found
    $defaultUser = ($homeUsers -split "`n")[0].Trim()
    Write-Host "  Detected user: $defaultUser" -ForegroundColor Green

    # Check if [user] section already exists in wsl.conf
    $hasUserSection = wsl -d $distroImportName -- bash -c "grep -q '\[user\]' /etc/wsl.conf 2>/dev/null && echo yes || echo no" 2>$null
    $hasUserSection = ($hasUserSection -replace "`0", "").Trim()

    if ($hasUserSection -eq "yes") {
        Write-Host "  Default user already configured in /etc/wsl.conf." -ForegroundColor Green
    } else {
        wsl -d $distroImportName -- bash -c "echo '' | sudo tee -a /etc/wsl.conf > /dev/null; echo '[user]' | sudo tee -a /etc/wsl.conf > /dev/null; echo 'default=$defaultUser' | sudo tee -a /etc/wsl.conf > /dev/null"
        Write-Host "  Default user set to '$defaultUser' in /etc/wsl.conf." -ForegroundColor Green
    }
} else {
    Write-Host "  [WARNING] No users found in /home/. Default user will be root." -ForegroundColor Yellow
    Write-Host "  You can create a user later with: wsl -d $distroImportName -- adduser <username>" -ForegroundColor Yellow
}

# ---------- Step 6/8: Write .wslconfig ----------
Write-Host "`n[6/8] Writing .wslconfig..." -ForegroundColor Cyan

$wslconfigPath = Join-Path $env:USERPROFILE ".wslconfig"
$wc = $config.wslconfig

$wslconfigContent = @"
[wsl2]
memory=$($wc.memory)
processors=$($wc.processors)
swap=$($wc.swap)
swapFile=$($wc.swapFile)
guiApplications=$($wc.guiApplications.ToString().ToLower())
defaultVhdSize=$($wc.defaultVhdSize)
sparseVhd=$($wc.sparseVhd.ToString().ToLower())
"@

if (Test-Path $wslconfigPath) {
    Write-Host "  Existing .wslconfig found at $wslconfigPath" -ForegroundColor Yellow
    Write-Host "  Current contents:" -ForegroundColor Yellow
    Get-Content $wslconfigPath | ForEach-Object { Write-Host "    $_" }
    Write-Host ""
    $response = Read-Host "  Overwrite with new config? (Y/N)"
    if ($response -ne 'Y' -and $response -ne 'y') {
        Write-Host "  Keeping existing .wslconfig." -ForegroundColor Yellow
    } else {
        Set-Content -Path $wslconfigPath -Value $wslconfigContent
        Write-Host "  .wslconfig updated." -ForegroundColor Green
    }
} else {
    Set-Content -Path $wslconfigPath -Value $wslconfigContent
    Write-Host "  .wslconfig created at $wslconfigPath" -ForegroundColor Green
}

# Create swap directory if needed
$swapDir = Split-Path $wc.swapFile -Parent
if ($swapDir -and -not (Test-Path $swapDir)) {
    New-Item -ItemType Directory -Force -Path $swapDir | Out-Null
    Write-Host "  Created swap directory: $swapDir" -ForegroundColor Green
}

# ---------- Step 7/8: Restart WSL and run Linux setup ----------
Write-Host "`n[7/8] Running Linux-side setup..." -ForegroundColor Cyan

Write-Host "  Shutting down WSL to apply .wslconfig..." -ForegroundColor Yellow
wsl --shutdown
Start-Sleep -Seconds 2

# Compute the WSL path for the script directory
$winPath = $PSScriptRoot
# Convert Windows path to WSL path: C:\foo\bar -> /mnt/c/foo/bar
$wslPath = $winPath -replace '\\', '/'
if ($wslPath -match '^([A-Za-z]):(.*)') {
    $wslPath = "/mnt/$($Matches[1].ToLower())$($Matches[2])"
}

# Phase 1: enable systemd
Write-Host "  Running _setup_ubuntu.sh --phase 1 (enable systemd)..." -ForegroundColor Yellow
wsl -d $distroImportName -- bash -c "cd '$wslPath' && bash _setup_ubuntu.sh --phase 1"

# Restart WSL for systemd to take effect
Write-Host "  Restarting WSL for systemd..." -ForegroundColor Yellow
wsl --shutdown
Start-Sleep -Seconds 3

# Phase 2: install packages
Write-Host "  Running _setup_ubuntu.sh --phase 2 (install packages)..." -ForegroundColor Yellow
wsl -d $distroImportName -- bash -c "cd '$wslPath' && bash _setup_ubuntu.sh --phase 2"

# ---------- Step 8/8: Done ----------
Write-Host "`n[8/8] Setup complete!" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Your WSL2 Ubuntu environment is ready on ${driveLetter}: drive." -ForegroundColor Green
Write-Host "  WSLg is enabled for GUI applications." -ForegroundColor Green
Write-Host ""
Write-Host "  To launch apps, open Ubuntu and run:" -ForegroundColor Green
Write-Host "    code &              # VS Code" -ForegroundColor White
Write-Host "    intellij-idea-community &  # IntelliJ IDEA" -ForegroundColor White
Write-Host "    pycharm-community &        # PyCharm" -ForegroundColor White
Write-Host "    nautilus &          # File Manager" -ForegroundColor White
Write-Host ""
Write-Host "  Run verify_setup.ps1 to verify the installation." -ForegroundColor Green
Read-Host "Press Enter to exit"
