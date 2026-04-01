@echo off
setlocal

:: Build and package linwin using pyship.
:: Creates a frozen executable and NSIS installer in the _pyship/ directory.

:: Run from the project root (one level up from scripts/)
cd /d "%~dp0\.."

echo === Building linwin with pyship ===
echo.

:: Ensure dependencies (including pyship) are installed
echo Syncing dependencies...
uv sync --group dev
if %errorlevel% neq 0 (
    echo ERROR: Failed to sync dependencies.
    pause
    exit /b 1
)
echo.

:: Clean stale build artifacts so pyship picks up the current version (this should be temporary until pyship >= 0.6.0)
if exist dist rmdir /s /q dist
if exist app rmdir /s /q app
if exist linwin.nsi del linwin.nsi

:: Run pyship to freeze and create installer
echo Running pyship...
uv run python -m pyship
if %errorlevel% neq 0 (
    echo ERROR: pyship failed.
    pause
    exit /b 1
)



