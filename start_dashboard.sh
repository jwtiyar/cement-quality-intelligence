#!/bin/bash
echo "Initializing AI Cement Dashboard..."
cd "$(dirname "$0")"
source venv/bin/activate

echo "==========================================="
echo "1. Scanning Excel Reports for new data..."
echo "==========================================="
./venv/bin/python build_dataset.py

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

