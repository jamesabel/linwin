@echo off
setlocal

:: Run from the project root (one level up from scripts/)
cd /d "%~dp0\.."

:: Run the test suite
uv run python -m pytest tests/ -v
