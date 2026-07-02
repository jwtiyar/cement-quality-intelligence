# Cement Plant AI Dashboard & Optimization System

An intelligent, full-stack dashboard for cement plant quality control. This application continuously learns from historical daily reports (Excel files), predicts 28-day cement strength using machine learning, detects manual data entry anomalies, and optimizes raw mix proportions for optimal clinker chemistry.

## Key Features

- **Machine Learning Strength Prediction:** Automatically trains XGBoost models on your historical data (spanning 10+ years) to predict 28-day compressive strength based on early strength (2/3 day), chemistry, and fineness. Separate models are trained dynamically for OPC, SRC, and SBC.
- **Raw Mix Optimization Solver:** Enter the chemistry of your raw materials (Limestone, Clay, Iron Ore, etc.) and target moduli (LSF, SM, AM). The solver automatically calculates the optimal blend proportions, predicts resulting clinker chemistry (SiO₂, Al₂O₃, Fe₂O₃, CaO), Bogue phases (C₃S, C₂S, C₃A, C₄AF), and ensures Liquid Phase content is within safe sintering limits (23%-29%).
- **Automated Anomaly Detection:** Validates thousands of historical daily report records against strict ASTM C150 and EN 197-1 chemical/strength standards. Suspicious values (like typos in Excel sheets) trigger smart alerts in the dashboard UI indicating the date, cement type, and out-of-bounds parameter.
- **Dynamic Excel Synchronization:** Extracts and cleans data from messy historical daily report Excel files dynamically. A single click in the UI syncs the latest data without needing server restarts.

## Installation & Setup

### Prerequisites
- Python 3.10 or newer installed on your system.
- Git (optional, if you want to clone from a repository instead of copying files).

### Environment Setup (Windows)
1. Double-click the `start_dashboard.bat` script.
2. The script will automatically:
   - Create a virtual environment (`venv`).
   - Install all required libraries (`fastapi`, `uvicorn`, `pandas`, `xgboost`, `scikit-learn`, etc.).
   - Scan your Excel reports and construct the initial consolidated CSV.
   - Boot up the local server.

### Environment Setup (Linux/macOS)
1. Open a terminal in the project directory.
2. Run the initialization script:
   ```bash
   ./start_dashboard.sh
   ```
3. If you encounter permission issues, make the script executable first:
   ```bash
   chmod +x start_dashboard.sh
   ```

## Usage Instructions

1. **Accessing the Application:** 
   Once the server is running, open your web browser and go to: `http://127.0.0.1:8500`

2. **Syncing New Data:**
   When plant operators add new daily reports or modify existing Excel files on the network drive, simply click the **"Sync Live Excel Data"** button at the top of the dashboard. The system will scan the folders, parse the sheets, rebuild the dataset, and retrain the machine learning models entirely in-memory.

3. **Predicting Strength:**
   In the bottom-right corner of the dashboard, you can test theoretical chemical compositions. Select the cement type, enter the chemistry and early strength, and hit "Predict" to see what the machine learning model expects the 28-day strength to be based on your historical plant data.

4. **Optimizing Raw Mix:**
   Go to the "Raw Mix Solver" tab or section (if integrated into the UI) to input material compositions and get target proportions. If a specific chemical target is physically impossible with the given raw materials, the system will output a clear error explaining the constraint violation.

## Troubleshooting

- **"Port 8500 is already in use"**: The server is already running in the background. Use `./stop_dashboard.sh` on Linux, or close the terminal window running the Python server.
- **"Typo Alert Banner shows up"**: The system found values in your Excel files that violate cement chemistry standards. Open the original Excel file for the mentioned date, correct the typo, and click "Sync Live Excel Data" on the dashboard to clear the alert.
- **"Server failed to start"**: Ensure all your `Daily Report 202X.xlsx` files are correctly located in their respective `[Year]` folders relative to this directory.

## Project Architecture

- `app.py`: The main entry point that starts the Uvicorn web server.
- `routes.py`: Defines all FastAPI backend endpoints (`/api/data`, `/api/refresh`, `/api/rawmix/calculate`, etc.).
- `state.py`: Manages the in-memory data cache, generates the anomaly detection lists, and performs global state management.
- `build_dataset.py`: Scans and parses messy historical Excel files into a clean pandas DataFrame (`ALL_CEMENT_DATA.csv`).
- `ml_train.py`: Trains the XGBoost Regressors on the historical CSV data.
- `rawmix_solver.py`: Contains the linear algebra optimization logic for calculating material proportions based on moduli targets.
- `dashboard/`: Contains the frontend HTML, CSS, and Vanilla JavaScript.
