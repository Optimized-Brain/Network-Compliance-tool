@echo off
echo ============================================================
echo   Network Switch Compliance Checker - Setup ^& Launch
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

:: Create virtual environment if not exists
if not exist "venv" (
    echo [*] Creating virtual environment...
    python -m venv venv
)

:: Activate virtual environment
call venv\Scripts\activate.bat

:: Install dependencies
echo [*] Installing dependencies...
pip install -r requirements.txt --quiet

:: Set mode (demo or live)
if "%1"=="live" (
    set COMPLIANCE_MODE=live
    echo [*] Mode: LIVE - Will connect to real switches via SSH
) else (
    set COMPLIANCE_MODE=demo
    echo [*] Mode: DEMO - Using simulated switch data
)

echo.
echo ============================================================
echo   Starting server at http://localhost:5000
echo   Press Ctrl+C to stop
echo ============================================================
echo.

:: Launch the application
python app.py

pause
