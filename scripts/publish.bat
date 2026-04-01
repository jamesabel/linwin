@echo off
setlocal

:: Build and upload linwin to PyPI.
:: Requires a PyPI API token configured via:
::   keyring set https://upload.pypi.org/legacy/ __token__

:: Run from the project root (one level up from scripts/)
cd /d "%~dp0\.."

echo === Publishing linwin to PyPI ===
echo.

:: Clean stale artifacts
if exist dist rmdir /s /q dist
echo Cleaned dist/
echo.

:: Build wheel and sdist
echo Building package...
uv build
if %errorlevel% neq 0 (
    echo ERROR: Build failed.
    pause
    exit /b 1
)
echo.

:: Validate metadata
echo Checking package metadata...
uv run twine check dist/*
if %errorlevel% neq 0 (
    echo ERROR: Package metadata check failed.
    pause
    exit /b 1
)
echo.

:: Upload to PyPI
echo Uploading to PyPI...
uv run twine upload dist/*
if %errorlevel% neq 0 (
    echo ERROR: Upload failed.
    pause
    exit /b 1
)

echo.
echo === Published successfully ===
