@echo off
setlocal

:: Check if uv is available
where uv >nul 2>&1
if %errorlevel% neq 0 (
    echo uv not found. Please run install.bat first.
    pause
    exit /b 1
)

uv run python _setup_tui.py
