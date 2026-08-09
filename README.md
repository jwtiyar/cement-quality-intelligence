# Cement Plant AI Dashboard & Optimization System

An intelligent, full-stack dashboard for cement plant quality control. This application continuously learns from historical daily reports (Excel files), predicts 28-day cement strength using machine learning, detects manual data entry anomalies, and optimizes raw mix proportions for optimal clinker chemistry.

## Key Features

- **Machine Learning Strength Prediction:** Automatically trains XGBoost models on your historical data (spanning 10+ years) to predict 28-day compressive strength based on early strength (2/3 day), chemistry, and fineness. Separate models are trained dynamically for OPC, SRC, and SBC. Validation is chronological (train on oldest 80%, validate on newest 20%) so reported R² and RMSE are honest forward-prediction numbers.
- **Raw Mix Optimization Solver:** Enter the chemistry of your raw materials (Limestone, Clay, Iron Ore, etc.) and target moduli (LSF, SM, AM). The solver validates inputs, calculates the optimal blend proportions, predicts resulting clinker chemistry (SiO₂, Al₂O₃, Fe₂O₃, CaO), Bogue phases (C₃S, C₂S, C₃A, C₄AF), and ensures Liquid Phase content is within safe sintering limits (23%-29%). When targets are simultaneously unreachable with the given materials, the solver falls back to the closest feasible mix and reports residuals + infeasibility instead of returning physically impossible negative proportions.
- **AI Process & Quality Assistant (RAG & Live Data):** Chat with your plant manuals, ASTM standards, or textbooks right inside the dashboard. A local TF-IDF search engine retrieves the exact relevant paragraphs and pages, while **Google GenAI SDK (Gemini)** synthesizes operational troubleshooting responses. Additionally, the assistant has direct awareness of your live plant laboratory dataset (daily, weekly, and monthly quality trends and test records). Chat output is HTML-escaped before rendering to prevent prompt-injection XSS.
- **Automated Anomaly Detection:** Validates thousands of historical daily report records against strict ASTM C150 and EN 197-1 chemical/strength standards. Suspicious values (like typos in Excel sheets) trigger smart alerts in the dashboard UI indicating the date, cement type, and out-of-bounds parameter.
- **Dynamic Excel Synchronization:** Extracts and cleans data from messy historical daily report Excel files dynamically. A single click in the UI syncs the latest data without needing server restarts. Writes are atomic (temp file + rename) so a crash mid-export can never leave a truncated CSV or index.

## Public Repository and Local Files

The repository contains the application code, tests, frontend, and chemistry
logic. Plant data and reference material are intentionally kept local and are
not included in the public repository.

### Required for the dashboard

- `ALL_CEMENT_DATA.csv` — the local consolidated plant dataset. It is ignored
  by Git. Provide it yourself, or let `build_dataset.py` create it from the
  year folders described below.
- Either an existing `ALL_CEMENT_DATA.csv` or at least one supported Excel
  daily report in a parent year folder. The server cannot start with no data.

### Optional local files

- `knowledge_base/` — local PDFs or text manuals for the RAG assistant. The
  folder and generated `rag_index.pkl` are ignored by Git. The core dashboard,
  chemistry analysis, raw-mix solver, and ML pipeline do not require manuals.
- `.env` with `GEMINI_API_KEY` or `GOOGLE_API_KEY` — required only for Gemini
  chat responses. It is not required for the offline dashboard and solver.
- `rawmix/` reference files — local PDFs, spreadsheets, Word documents, and
  helper files may be placed here for offline work, but they are ignored and
  not redistributed. The public root-level `rawmix_solver.py` and dashboard
  are sufficient for raw-mix calculations; the local reference files are not
  required to run the solver.
- `venv/` — created locally by the startup scripts and ignored by Git.

`dashboard/data.json` is not included and is not used by the application. The
dashboard receives its data from the live `/api/data` endpoint after the local
CSV is loaded.

## Data Directory Structure & Excel Formatting

For the application to find and read your daily report data, your files must be structured in specific year folders located **one level above** this app's directory. 

### 1. Folder Structure
The app looks at the parent directory for folders named as years (e.g., `2023`, `2024`, `2025`, `2026`). Place your Excel files inside their respective year folders:
```text
daily results/                   <-- (Parent Directory)
│
├── 2024/
│   └── Daily Report 2024.xlsx
├── 2025/
│   └── Daily Report 2025.xlsx
├── 2026/
│   └── Daily Report 2026.xlsx
│
└── cement_app/                  <-- (This App's Directory)
    ├── app.py
    ├── build_dataset.py
    └── ...
```

### 2. Excel Sheet Requirements
When the extraction script runs, it opens the Excel files and looks for specific sheet names:
* **Primary:** The script looks for a tab exactly named **"Daily Report"**. 
* **Fallback:** If "Daily Report" is missing, it will look for tabs explicitly named **"OPC"**, **"SRC"**, or **"SBC"**.

### 3. Missing Data / Empty Folders
If you run this application and the year folders (`202X`) are missing from the parent directory:
* The scanner will log **"No records found!"** and skip database creation.
* The application server will intentionally **refuse to start** and will crash, because it cannot run machine learning models or display dashboards with zero data.

## Installation & Setup

### Prerequisites
- Python 3.10 or newer installed on your system.
- Git (optional, if you want to clone from a repository instead of copying files).
- A Gemini API Key (needed for the AI Chat Assistant).

### 1. Environment Setup (Windows)
1. Double-click the `start_dashboard.bat` script.
2. The script will automatically:
    - Create a virtual environment (`venv`).
    - Run `_check_deps.py` to verify all required libraries are installed (versions are pinned in `requirements.txt`), installing missing packages automatically if needed.
    - Scan your Excel reports and construct the initial consolidated CSV.
    - Boot up the local server.

### 2. Environment Setup (Linux/macOS)
1. Open a terminal in the project directory.
2. Run the initialization script:
    ```bash
    ./start_dashboard.sh
    ```
3. If you encounter permission issues, make the script executable first:
    ```bash
    chmod +x start_dashboard.sh
    ```

### 3. Setup Gemini API Key
To enable the AI chat feature, configure your API key in a `.env` file in the project folder:
```bash
printf "Enter GEMINI_API_KEY (typing hidden): " && read -s val && echo && echo "GEMINI_API_KEY=$val" >> ".env" && echo "Saved."
```

### 4. Index Knowledge Base Manuals
1. Drop your PDF textbooks, standards, or manuals into the `cement_app/knowledge_base/` folder.
2. Open the dashboard at `http://127.0.0.1:8500`, switch to the **"AI Assistant & Manuals"** tab, and click the green **"Rebuild Vector Index"** button.
3. The indexer will instantly parse your files locally and sync them with the chatbot.

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

## Tests

```bash
cd cement_app
./venv/bin/python -m pytest tests/ -v
```

99 tests covering: chemistry math (moduli, Bogue phases, liquid content, diagnostics, phase validity flags), the raw-mix solver (solve/recipe modes, constrained infeasible targets, input validation, residuals/feasibility status), dataset normalization (real CSV), Pydantic API validation (422 boundary tests), ML training sanity (chronological validation, confidence labels), and `.env` parsing. Run `./venv/bin/python verify_cement_logic.py` for the FLS-reference verification report.

## Smoke test (optional, requires Playwright)

```bash
# one-time setup (needs ~110 MB free in the temporary directory):
TMPDIR="${TMPDIR:-/tmp}/cement-app-playwright" npx playwright install firefox
node tests/smoke_dashboard.mjs
```

The script boots the server, loads the dashboard in a real Firefox browser, clicks through the raw-mix solver, and fails on any uncaught JS error.

## Project Architecture

- `app.py`: The main entry point that starts the Uvicorn web server.
- `routes.py`: Defines all FastAPI backend endpoints, including the RAG `/api/chat` and `/api/rag/rebuild` handlers. Request bodies are validated by Pydantic models in `schemas.py`.
- `schemas.py`: Strict Pydantic request models for every POST endpoint (oxide ranges 0–100, positive targets, literal cement types). Invalid payloads return structured 422 errors.
- `rag_index.py`: Local TF-IDF search index builder. Extracts text from PDFs and builds a search index saved to `knowledge_base/rag_index.pkl`. Writes are atomic (temp + rename).
- `state.py`: Manages the in-memory data cache, generates the anomaly detection lists, and performs global state management. Dataset summary writes are atomic.
- `build_dataset.py`: Scans and parses messy historical Excel files into a clean pandas DataFrame (`ALL_CEMENT_DATA.csv`). The CSV write is atomic.
- `ml_train.py`: Trains the XGBoost Regressors on the historical CSV data. Features include chemistry oxides, early strength (2/3-day), fineness, **7-day strength** and **80 µm sieve residue** — the two strongest predictors of 28-day strength (correlation +0.92 / −0.82). **Training uses a chronological split** (earliest 80% train, most recent 20% validate) so reported metrics are honest forward-prediction numbers, not random-split leakage. All models currently report `chemistry_only` confidence (R² negative on the forward period).
- `rawmix_solver.py`: Contains the linear algebra optimization logic for calculating material proportions based on moduli targets. Validates all inputs (finite oxides, LOI/H2O in [0,100), positive calorific value and targets, non-negative recipes). When the exact 4×4 solve yields negative proportions, falls back to a bounded SLSQP least-squares solve and reports residuals + `feasible`/`infeasible` status.
- `chemistry.py`: Single source of truth for Boge phase calculations, liquid content, and moduli. `calc_bogue()` returns raw values (no silent clamping) and `analyze_clinker()` flags physically impossible compositions via `phases_valid` / `negative_phases`.
- `dashboard/`: Contains the frontend HTML, CSS, and Vanilla JavaScript. AI chat output is HTML-escaped before rendering to prevent prompt-injection XSS.
