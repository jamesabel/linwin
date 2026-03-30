@echo off
setlocal

:: Switch to UTF-8 so Textual's Unicode characters render correctly
chcp 65001 >nul 2>&1

:: Run from the directory where this script lives
cd /d "%~dp0"

:: Launch the TUI
set PYTHONIOENCODING=utf-8
uv run python -m tui.windows
