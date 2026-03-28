@echo off
setlocal

echo === WSL Ubuntu GNOME Setup - Install ===
echo.

:: Check if uv is already installed
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

:: Install Python via uv
echo Installing Python...
uv python install
if %errorlevel% neq 0 (
    echo ERROR: Failed to install Python.
    pause
    exit /b 1
)
echo.

:: Sync project dependencies from pyproject.toml
echo Installing project dependencies...
uv sync
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)
echo.

echo === Installation complete ===
echo.
echo To run the setup TUI:
echo   uv run python _setup_tui.py
echo.
pause
