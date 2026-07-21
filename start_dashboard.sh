#!/bin/bash
echo "Initializing AI Cement Dashboard..."
cd "$(dirname "$0")"
source venv/bin/activate

echo "==========================================="
echo "0. Verifying all dependencies..."
echo "==========================================="
./venv/bin/python _check_deps.py
if [ $? -ne 0 ]; then
    echo "Missing packages detected. Installing..."
    pip install -r requirements.txt --quiet
    ./venv/bin/python _check_deps.py
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
    ./venv/bin/python build_dataset.py
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
./venv/bin/python app.py
