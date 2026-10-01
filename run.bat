@echo off
title PO LLM Translator
cd /d "%~dp0"

echo ========================================================
echo               PO LLM Translator Launcher
echo ========================================================
echo Checking Python environment...

set "PYTHON_EXE=python"
if exist "%~dp0.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
    echo [OK] Using virtual environment: .venv
    goto :ready
)
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
    echo [OK] Using virtual environment: venv
    goto :ready
)

echo [OK] Using system Python

:ready
"%PYTHON_EXE%" -c "import po_translator, PySide6" >nul 2>nul
if %errorlevel% neq 0 (
    echo Installing package dependencies...
    "%PYTHON_EXE%" -m pip install -e "%~dp0"
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install package dependencies!
        pause
        exit /b 1
    )
)

echo Starting PO LLM Translator GUI...
"%PYTHON_EXE%" -m po_translator.main
if %errorlevel% neq 0 (
    echo.
    echo Application exited with code: %errorlevel%
    pause
)
