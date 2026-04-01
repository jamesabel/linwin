@echo off
setlocal

:: Create and configure the local development .venv
:: Run from the project root (one level up from scripts/)
cd /d "%~dp0\.."

echo === linwin Development Environment Setup ===
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

:: Create .venv and sync all dependencies (including dev group)
echo Syncing project dependencies (runtime + dev)...
uv sync --group dev
if %errorlevel% neq 0 (
    echo ERROR: Failed to sync dependencies.
    pause
    exit /b 1
)
echo.

echo === Development environment ready ===
echo.
echo   Activate:  .venv\Scripts\activate
echo   Run app:   uv run python -m linwin.windows
echo   Run tests: uv run pytest tests/ -v
echo   Ship:      scripts\ship.bat
echo.
