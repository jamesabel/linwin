@echo off
setlocal

:: Switch to UTF-8 so Textual's Unicode characters render correctly
chcp 65001 >nul 2>&1

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

:: Sync project dependencies
echo Syncing project dependencies...
uv sync
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo.

:: Launch the setup TUI
set PYTHONIOENCODING=utf-8
uv run python -m linwin.windows
