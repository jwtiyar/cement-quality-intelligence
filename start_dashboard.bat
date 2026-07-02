@echo off
echo ========================================================
echo   Initializing AI Cement Dashboard on Windows
echo ========================================================
cd /d "%~dp0"

REM 1. Set up and activate Virtual Environment
if not exist venv (
    echo [INFO] Virtual environment 'venv' not found. Creating a new one...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [ERROR] Python is not installed or not in PATH. Please install Python 3.10+ and try again.
        pause
        exit /b %errorlevel%
    )
    echo [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
    echo [INFO] Installing required packages from requirements.txt...
    pip install -r requirements.txt
) else (
    echo [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM 2. Dynamic check for missing dependencies
python -c "import fastapi" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Missing required packages detected. Installing/updating dependencies...
    pip install -r requirements.txt
)

echo.
echo ===========================================
echo 1. Checking Dataset...
echo ===========================================
if not exist ALL_CEMENT_DATA.csv (
    echo [INFO] Dataset not found. Scanning Excel Reports for the first time...
    python build_dataset.py
    if %errorlevel% neq 0 (
        echo [WARNING] Scanning failed. Make sure Excel reports are in the correct directories.
    )
) else (
    echo [INFO] Dataset ALL_CEMENT_DATA.csv found. Skipping initial scan.
    echo (Use "Sync Live Excel Data" in the dashboard to update data later)
)

echo.
echo ===========================================
echo 2. Starting AI Dashboard Server...
echo ===========================================
echo Open your web browser and go to: http://127.0.0.1:8500
echo (Keep this window open to keep the server running. Press Ctrl+C to stop it.)
echo ===========================================
echo.

python app.py

pause
