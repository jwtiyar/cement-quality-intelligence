#!/bin/bash
echo "Initializing AI Cement Dashboard..."
cd "$(dirname "$0")"

# Detect Python & Pip in virtual environment (Windows vs Linux/macOS)
if [ -f "venv/Scripts/python.exe" ] || [ -f "venv/Scripts/python" ]; then
    PYTHON_CMD="venv/Scripts/python"
    PIP_CMD="venv/Scripts/pip"
    ACTIVATE_SCRIPT="venv/Scripts/activate"
elif [ -f "venv/bin/python" ]; then
    PYTHON_CMD="./venv/bin/python"
    PIP_CMD="./venv/bin/pip"
    ACTIVATE_SCRIPT="venv/bin/activate"
else
    PYTHON_CMD="python3"
    PIP_CMD="pip3"
    ACTIVATE_SCRIPT=""
fi

if [ ! -d "venv" ]; then
    echo "[INFO] Virtual environment 'venv' not found. Creating a new one..."
    if command -v python3 &>/dev/null; then
        python3 -m venv venv
    else
        python -m venv venv
    fi
    if [ $? -ne 0 ]; then
        echo "[ERROR] Python 3 is not installed or not in PATH. Please install Python 3.10+ and try again."
        exit 1
    fi
    if [ -f "venv/Scripts/activate" ]; then
        source venv/Scripts/activate
        PYTHON_CMD="venv/Scripts/python"
        PIP_CMD="venv/Scripts/pip"
    else
        source venv/bin/activate
        PYTHON_CMD="./venv/bin/python"
        PIP_CMD="./venv/bin/pip"
    fi
    echo "[INFO] Installing required packages from requirements.txt..."
    $PIP_CMD install -r requirements.txt --quiet
else
    if [ -n "$ACTIVATE_SCRIPT" ] && [ -f "$ACTIVATE_SCRIPT" ]; then
        echo "[INFO] Activating virtual environment ($ACTIVATE_SCRIPT)..."
        source "$ACTIVATE_SCRIPT"
    fi
fi

echo "==========================================="
echo "0. Verifying all dependencies..."
echo "==========================================="
$PYTHON_CMD _check_deps.py
if [ $? -ne 0 ]; then
    echo "Missing packages detected. Installing..."
    $PIP_CMD install -r requirements.txt --quiet
    $PYTHON_CMD _check_deps.py
    if [ $? -ne 0 ]; then
        echo "[ERROR] Some packages failed to install."
        exit 1
    fi
fi

echo "==========================================="
echo "1. Checking Dataset..."
echo "==========================================="
if [ ! -f "ALL_CEMENT_DATA.csv" ]; then
    echo "Dataset not found. Scanning Excel Reports for the first time..."
    $PYTHON_CMD build_dataset.py
else
    echo "Dataset ALL_CEMENT_DATA.csv found. Skipping initial scan."
    echo "(Use 'Sync Live Excel Data' in the dashboard to update data later)"
fi

echo ""
echo "==========================================="
echo "2. Starting AI Dashboard Server..."
echo "==========================================="
# Kill any existing server first just in case
pkill -f "app.py" 2>/dev/null

echo "Open your web browser and go to: http://127.0.0.1:8500"
echo "Keep this terminal open to keep the server running. Press Ctrl+C to stop it."
echo "==========================================="
echo ""
$PYTHON_CMD app.py
