@echo off
setlocal

:: Switch to UTF-8 so Textual's Unicode characters render correctly
chcp 65001 >nul 2>&1

:: Run from the project root (one level up from scripts/)
cd /d "%~dp0\.."

echo === WSL Ubuntu GNOME Setup ===
echo.

:: Ensure uv is installed
where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo uv is already installed.
) else (
    echo Installing uv...
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install uv.
        pause
        exit /b 1
    )
    echo uv installed.
)
echo.

:: Ensure Python is installed
echo Ensuring Python is installed...
uv python install
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Python.
    pause
    exit /b 1
)
echo.

:: Compute a date 7 days ago (YYYY-MM-DD) for supply-chain security.
:: Only install packages published at least 1 week ago so the community
:: has time to discover compromises or vulnerabilities.
for /f %%d in ('powershell -NoProfile -Command "(Get-Date).AddDays(-7).ToString('yyyy-MM-dd')"') do set EXCLUDE_DATE=%%d
echo Security: excluding packages newer than %EXCLUDE_DATE% (1 week ago)

:: Sync project dependencies
echo Syncing project dependencies...
uv sync --exclude-newer "%EXCLUDE_DATE%"
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo.

:: Launch the setup TUI
set PYTHONIOENCODING=utf-8
uv run python -m linwin.windows
