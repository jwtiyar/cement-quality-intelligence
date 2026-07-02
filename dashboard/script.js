let trendChart = null;
let monthlyChart = null;
let distributionChart = null;
let importanceChart = null;
let dashboardData = null;

const CEMENT_COLORS = {
    OPC: { border: '#38bdf8', bg: 'rgba(56, 189, 248, 0.08)' },
    SRC: { border: '#10b981', bg: 'transparent' },
    SBC: { border: '#8b5cf6', bg: 'transparent' }
};


document.addEventListener('DOMContentLoaded', async () => {
    
    // Sync the hidden native date picker with the visible dd/mm/yyyy text box
    const searchDateInput = document.getElementById('searchDate');
    const searchDateDisplay = document.getElementById('searchDateDisplay');
    if (searchDateInput && searchDateDisplay) {
        searchDateInput.addEventListener('change', (e) => {
            const val = e.target.value; // Always YYYY-MM-DD
            if (val) {
                const parts = val.split('-');
                if (parts.length === 3) {
                    searchDateDisplay.value = `${parts[2]}/${parts[1]}/${parts[0]}`;
                }
            }
        });
    }

    const btnSync = document.getElementById('btnSync');
    if (btnSync) {
        btnSync.addEventListener('click', async () => {
            const originalText = btnSync.innerHTML;
            btnSync.innerHTML = '⏳ Extracting...';
            btnSync.disabled = true;
            try {
                const res = await fetch('/api/refresh', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    btnSync.innerHTML = '✅ Synced!';
                    
                    if (data.new_records && data.new_records.length > 0) {
                        let msg = `Success! Fetched ${data.new_records.length} new daily reports:\n\n`;
                        const samples = data.new_records.slice(0, 10).map(r => `• ${r.date} (${r.type})`).join('\n');
                        msg += samples;
                        if (data.new_records.length > 10) msg += `\n...and ${data.new_records.length - 10} more.`;
                        alert(msg);
                    } else {
                        alert('Sync complete! The sheets were scanned but no new daily reports were found.');
                    }
                    
                    window.location.reload();
                } else {
                    btnSync.innerHTML = '❌ Error';
                    alert('Failed to sync data.');
                    setTimeout(() => { btnSync.innerHTML = originalText; btnSync.disabled = false; }, 2000);
                }
            } catch (e) {
                btnSync.innerHTML = '❌ Error';
                alert('Network error syncing data.');
                setTimeout(() => { btnSync.innerHTML = originalText; btnSync.disabled = false; }, 2000);
            }
        });
    }

    try {
        const response = await fetch('/api/data');
        if (!response.ok) throw new Error('API server returned error');
        dashboardData = await response.json();
        
        // 1. Populate Summary Statistics
        document.getElementById('totalRecords').innerText = dashboardData.summary.totalRecords.toLocaleString();
        
        document.getElementById('avgStrength').innerHTML = `
            <div style="font-size: 1.4rem; display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.5rem;">
                <div><span style="color: #38bdf8; font-size: 0.95rem; display: inline-block; width: 45px; text-align: left;">OPC:</span> ${dashboardData.summary.avgStrength.OPC || '--'} <span class="unit">MPa</span></div>
                <div><span style="color: #10b981; font-size: 0.95rem; display: inline-block; width: 45px; text-align: left;">SRC:</span> ${dashboardData.summary.avgStrength.SRC || '--'} <span class="unit">MPa</span></div>
                <div><span style="color: #8b5cf6; font-size: 0.95rem; display: inline-block; width: 45px; text-align: left;">SBC:</span> ${dashboardData.summary.avgStrength.SBC || '--'} <span class="unit">MPa</span></div>
            </div>`;
            
        document.getElementById('avgC3S').innerHTML = `
            <div style="font-size: 1.4rem; display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.5rem;">
                <div><span style="color: #38bdf8; font-size: 0.95rem; display: inline-block; width: 45px; text-align: left;">OPC:</span> ${dashboardData.summary.avgC3S.OPC || '--'} <span class="unit">%</span></div>
                <div><span style="color: #10b981; font-size: 0.95rem; display: inline-block; width: 45px; text-align: left;">SRC:</span> ${dashboardData.summary.avgC3S.SRC || '--'} <span class="unit">%</span></div>
                <div><span style="color: #8b5cf6; font-size: 0.95rem; display: inline-block; width: 45px; text-align: left;">SBC:</span> ${dashboardData.summary.avgC3S.SBC || '--'} <span class="unit">%</span></div>
            </div>`;

        document.getElementById('yearsCoverage').innerText = dashboardData.summary.yearsCoverage;

        // 2. Setup Chart Parameter Selection
        const paramSelector = document.getElementById('paramSelector');
        paramSelector.addEventListener('change', (e) => {
            updateChart(e.target.value);
            updateEraSubtitle(e.target.value);
        });

        // Initialize with default 28-day Strength
        initChart('Strength_28D');
        updateEraSubtitle('Strength_28D');

        // 3. Populate Correlation Matrix (Heatmap Table)
        buildCorrelationTable();

        // 4. Setup ML Predictor
        setupMLPredictor();

        // 5. Populate lowest-strength table
        populateLowStrengthDays();

        // 6. New Interactive Charts
        initDistributionChart();
        initImportanceChart(document.getElementById('predictCementType').value);

        // 7. Setup Monthly Analysis Chart
        setupMonthlyChart();

        // 8. Setup Raw Mix Calculator
        setupRawMixCalculator();

        // 9. Export CSV button
        const btnExport = document.getElementById('btnExportCSV');
        if (btnExport) {
            btnExport.addEventListener('click', () => {
                window.location.href = '/api/export/csv';
            });
        }

    } catch (error) {
        console.error('Error loading dashboard data:', error);
        document.querySelector('.container').innerHTML = `
            <div class="glass" style="padding: 2.5rem; text-align: center; color: #ef4444; max-width: 600px; margin: 3rem auto;">
                <h2>Error Initializing Dashboard</h2>
                <p style="margin: 1rem 0; color: #94a3b8;">Ensure the FastAPI server is running (e.g. <code>./start_dashboard.sh</code>) and is accessible at <code>http://127.0.0.1:8500</code>.</p>
                <p style="font-size: 0.85rem; color: #64748b; font-family: monospace;">${error.message}</p>
            </div>
        `;
    }
});

// ─── Era-boundary vertical line plugin ──────────────────────────────────────
// Draws a dashed amber vertical line at the year where 28D data starts being
// reliably available, plus a small label. Only visible for Strength_28D param.
let _eraLineActive = false;
const eraLinePlugin = {
    id: 'eraLine',
    afterDraw(chart) {
        if (!_eraLineActive) return;
        const eraYear = String(dashboardData.strength28Era);
        if (!eraYear) return;
        const labels = chart.data.labels;
        const eraIndex = labels.indexOf(eraYear);
        if (eraIndex < 0) return;

        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data || !meta.data[eraIndex]) return;
        const x = meta.data[eraIndex].x;
        const { top, bottom } = chart.chartArea;
        const ctx = chart.ctx;

        ctx.save();

        // Shaded region: before era (sparse data zone)
        ctx.fillStyle = 'rgba(245, 158, 11, 0.04)';
        ctx.fillRect(chart.chartArea.left, top, x - chart.chartArea.left, bottom - top);

        // Dashed vertical line
        ctx.beginPath();
        ctx.setLineDash([6, 4]);
        ctx.strokeStyle = 'rgba(245, 158, 11, 0.65)';
        ctx.lineWidth = 1.5;
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.stroke();

        // Label background
        const label = `28D data from ${eraYear} →`;
        ctx.setLineDash([]);
        ctx.font = "500 11px 'Outfit', sans-serif";
        const tw = ctx.measureText(label).width;
        const lx = x + 5;
        const ly = top + 14;
        ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
        ctx.beginPath();
        ctx.roundRect(lx - 3, ly - 11, tw + 8, 18, 4);
        ctx.fill();

        // Label text
        ctx.fillStyle = 'rgba(245, 158, 11, 0.9)';
        ctx.textBaseline = 'top';
        ctx.fillText(label, lx + 1, ly - 9);

        // Left-side label: sparse zone
        const sparseLabel = '← Early strength (2D/3D)';
        ctx.font = "400 10px 'Outfit', sans-serif";
        const sw = ctx.measureText(sparseLabel).width;
        const sx = Math.max(chart.chartArea.left + 4, x - sw - 8);
        ctx.fillStyle = 'rgba(15, 23, 42, 0.65)';
        ctx.beginPath();
        ctx.roundRect(sx - 3, ly - 11, sw + 8, 18, 4);
        ctx.fill();
        ctx.fillStyle = 'rgba(148, 163, 184, 0.7)';
        ctx.fillText(sparseLabel, sx + 1, ly - 9);

        ctx.restore();
    }
};
Chart.register(eraLinePlugin);
// ────────────────────────────────────────────────────────────────────────────

// Initialize Trend Chart
function initChart(param) {
    const ctx = document.getElementById('trendChart').getContext('2d');
    const paramData = dashboardData.trends.data[param];
    
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = "'Outfit', sans-serif";
    
    _eraLineActive = (param === 'Strength_28D') && !!dashboardData.strength28Era;

    const datasets = [
        {
            label: 'OPC (Ordinary Portland)', data: paramData.OPC,
            borderColor: CEMENT_COLORS.OPC.border, backgroundColor: CEMENT_COLORS.OPC.bg,
            borderWidth: 3, tension: 0.35, fill: true, spanGaps: false,
            pointBackgroundColor: CEMENT_COLORS.OPC.border,
            pointBorderColor: '#0f172a', pointBorderWidth: 2, pointRadius: 5, pointHoverRadius: 7
        },
        {
            label: 'SRC (Sulfate Resisting)', data: paramData.SRC,
            borderColor: CEMENT_COLORS.SRC.border, backgroundColor: CEMENT_COLORS.SRC.bg,
            borderWidth: 2, tension: 0.35, borderDash: [5, 5], pointRadius: 4, spanGaps: false
        },
        {
            label: 'SBC', data: paramData.SBC,
            borderColor: CEMENT_COLORS.SBC.border, backgroundColor: CEMENT_COLORS.SBC.bg,
            borderWidth: 2, tension: 0.35, borderDash: [5, 5], pointRadius: 4, spanGaps: false
        }
    ];

    trendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: dashboardData.trends.labels,
            datasets: datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { padding: 15, usePointStyle: true, pointStyle: 'circle' }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    titleFont: { size: 13, family: "'Outfit', sans-serif", weight: 'bold' },
                    bodyFont: { size: 12, family: "'Outfit', sans-serif" },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: true
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)', drawBorder: false }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)', drawBorder: false },
                    title: { display: true, text: getParamUnit(param), font: { size: 12 } }
                }
            },
            interaction: { mode: 'index', intersect: false }
        }
    });
}

// Update Trend Chart dynamically
function updateChart(param) {
    if (!trendChart) return;
    const paramData = dashboardData.trends.data[param];
    _eraLineActive = (param === 'Strength_28D') && !!dashboardData.strength28Era;
    trendChart.data.datasets[0].data = paramData.OPC;
    trendChart.data.datasets[1].data = paramData.SRC;
    trendChart.data.datasets[2].data = paramData.SBC;
    trendChart.options.scales.y.title.text = getParamUnit(param);
    trendChart.update();
}

function getParamUnit(param) {
    switch (param) {
        case 'Strength_28D': return '28-Day Strength (MPa)';
        case 'Strength_Early': return 'Early (2D/3D) Strength (MPa)';
        case 'C3S': return 'Tricalcium Silicate (C3S %)';
        case 'CaO': return 'Lime (CaO %)';
        case 'Fineness': return 'Fineness / Blaine (cm²/g)';
        case 'LSF': return 'Lime Saturation Factor (LSF)';
        default: return '';
    }
}

// Show/hide era annotation when viewing 28D strength
function updateEraSubtitle(param) {
    const subtitle = document.getElementById('trendChartSubtitle');
    if (!subtitle) return;
    const eraYear = dashboardData.strength28Era;
    if (param === 'Strength_28D' && eraYear) {
        subtitle.style.display = 'block';
        subtitle.innerHTML = `⚠️ 28-day strength data becomes reliably available from <strong>${eraYear}</strong> onward. Earlier years have sparse 28D records (mostly 2D/3D/7D only).`;
    } else {
        subtitle.style.display = 'none';
    }
}

// Generate Correlation Grid (Heatmap Table)
function buildCorrelationTable() {
    const table = document.getElementById('correlationTable');
    const cols = dashboardData.correlation.columns;
    const matrix = dashboardData.correlation.matrix;

    // Build header row
    let headerHTML = '<thead><tr><th>Feature</th>';
    cols.forEach(col => {
        headerHTML += `<th>${col.replace('_', ' ')}</th>`;
    });
    headerHTML += '</tr></thead>';

    // Build body rows
    let bodyHTML = '<tbody>';
    cols.forEach(rowCol => {
        bodyHTML += `<tr><td style="font-weight: 500; text-align: left; background: rgba(15, 23, 42, 0.4);">${rowCol.replace('_', ' ')}</td>`;
        cols.forEach(colCol => {
            const val = matrix[rowCol][colCol] || 0;
            const color = getCorrelationColor(val);
            bodyHTML += `<td style="background-color: ${color}; color: #ffffff; font-weight: bold;">${val.toFixed(2)}</td>`;
        });
        bodyHTML += '</tr>';
    });
    bodyHTML += '</tbody>';

    table.innerHTML = headerHTML + bodyHTML;
}

function getCorrelationColor(val) {
    if (val === 1.0) return 'rgba(56, 189, 248, 0.15)'; // Identity diagonal
    if (val > 0) {
        return `rgba(239, 68, 68, ${val * 0.7})`; // Positive = Red opacity
    } else {
        return `rgba(59, 130, 246, ${Math.abs(val) * 0.7})`; // Negative = Blue opacity
    }
}

// Setup ML prediction panel
function setupMLPredictor() {
    const cTypeSelect = document.getElementById('predictCementType');
    const searchDateInput = document.getElementById('searchDate');
    const btnLoadRecord = document.getElementById('btnLoadRecord');
    const searchFeedback = document.getElementById('searchFeedback');
    const actualResultBox = document.getElementById('actualResultBox');
    const actualStrengthVal = document.getElementById('actualStrengthVal');
    
    // Function to clear optimizer inputs and reset outputs
    function clearOptimizerInputs() {
        document.getElementById('opt_CaO').value = '';
        document.getElementById('opt_SiO2').value = '';
        document.getElementById('opt_Al2O3').value = '';
        document.getElementById('opt_Fe2O3').value = '';
        document.getElementById('opt_MgO').value = '';
        document.getElementById('opt_SO3').value = '';
        document.getElementById('opt_Strength_Early').value = '';
        document.getElementById('opt_Early_Strength_Days').value = '';
        document.getElementById('opt_Fineness').value = '';
        
        document.getElementById('opt_res_C3S').innerText = '--';
        document.getElementById('opt_res_C2S').innerText = '--';
        document.getElementById('opt_res_C3A').innerText = '--';
        document.getElementById('opt_res_C4AF').innerText = '--';
        document.getElementById('opt_res_LSF').innerText = '--';
        document.getElementById('opt_res_SM').innerText = '--';
        document.getElementById('opt_res_AM').innerText = '--';
        document.getElementById('opt_res_strength').innerText = '--';
        const adviceEl = document.getElementById('opt_advice');
        if (adviceEl) {
            adviceEl.innerHTML = 'Load a historical record above to start simulating and receiving AI advice...';
        }
    }

    // Function to update inputs and model stats based on selected cement type
    function updateModelUI(cType, recordData = null, force_reset = false) {
        const modelData = dashboardData.ml[cType];
        const r2El = document.getElementById('modelR2');
        const rmseEl = document.getElementById('modelRMSE');
        const confEl = document.getElementById('modelConfidence');
        const trainEl = document.getElementById('modelTrainInfo');

        r2El.innerText = `R² Score: ${(modelData.r2 * 100).toFixed(1)}%`;
        rmseEl.innerText = `RMSE: ${modelData.rmse} MPa`;

        const confColors = {
            predictive: '#10b981',
            exploratory: '#f59e0b',
            chemistry_only: '#94a3b8'
        };
        if (confEl) {
            confEl.innerText = modelData.confidenceLabel || '';
            confEl.style.color = confColors[modelData.confidence] || '#94a3b8';
        }
        if (trainEl) {
            const dr = modelData.strengthDateRange || {};
            const range = dr.min && dr.max ? `${dr.min} → ${dr.max}` : 'n/a';
            trainEl.innerText = `${modelData.trainSamples || 0} training rows (28D) · ${range}`;
        }

        if (recordData) {
            populateOptimizer(recordData);
        } else if (force_reset) {
            clearOptimizerInputs();
        } else {
            // Keep current values and just run simulation (if any inputs are filled)
            runOptimizationSimulation();
        }
    }

    // Initial setup with selected type - starts with empty inputs
    updateModelUI(cTypeSelect.value, null, true);

    // Helper function to load record for currently selected date and type
    async function loadRecordForSelectedDateAndType() {
        const dateVal = searchDateInput.value;
        const cType = cTypeSelect.value;
        
        if (!dateVal) return;

        searchFeedback.style.display = 'block';
        searchFeedback.style.color = '#94a3b8';
        searchFeedback.innerText = 'Searching...';

        try {
            const res = await fetch(`/api/record?date=${dateVal}&type=${cType}`);
            const resData = await res.json();

            if (resData.found) {
                // Populate inputs with record values
                updateModelUI(cType, resData.record);
                
                searchFeedback.style.color = '#10b981';
                searchFeedback.innerText = `Record loaded for ${dateVal}!`;
                
                // If 28-day actual strength exists
                if (resData.record.Strength_28D !== null) {
                    actualResultBox.style.display = 'flex';
                    actualStrengthVal.innerText = parseFloat(resData.record.Strength_28D).toFixed(1);
                } else {
                    actualResultBox.style.display = 'none';
                }
            } else {
                // Clear inputs
                updateModelUI(cType, null, true);
                searchFeedback.style.color = '#ef4444';
                searchFeedback.innerText = `No record found for ${dateVal} (${cType}). Inputs cleared.`;
                actualResultBox.style.display = 'none';
            }
        } catch (err) {
            console.error('Lookup failed:', err);
            searchFeedback.style.color = '#ef4444';
            searchFeedback.innerText = 'Error loading record from database.';
        }
    }

    // Update when dropdown changes (automatically fetches the latest date for that type and loads it)
    cTypeSelect.addEventListener('change', async (e) => {
        const cType = e.target.value;
        updateImportanceChart(cType);
        
        try {
            const res = await fetch(`/api/latest_date?type=${cType}`);
            const data = await res.json();
            if (data.found && data.date) {
                searchDateInput.value = data.date;
                searchDateInput.dispatchEvent(new Event('change'));
                loadRecordForSelectedDateAndType();
            } else {
                searchDateInput.value = '';
                if (searchDateDisplay) searchDateDisplay.value = '';
                updateModelUI(cType, null, true);
                actualResultBox.style.display = 'none';
                searchFeedback.style.display = 'none';
            }
        } catch (err) {
            console.error('Error fetching latest date:', err);
            updateModelUI(cType, null, true);
            actualResultBox.style.display = 'none';
            searchFeedback.style.display = 'none';
        }
    });

    // Handle Load Record Click
    btnLoadRecord.addEventListener('click', () => {
        const dateVal = searchDateInput.value;
        if (!dateVal) {
            alert('Please select a date first.');
            return;
        }
        loadRecordForSelectedDateAndType();
    });

    // --- AI Mix Optimizer & Simulator Logic ---
    const optInputs = ['opt_CaO', 'opt_SiO2', 'opt_Al2O3', 'opt_Fe2O3', 'opt_MgO', 'opt_SO3', 'opt_Strength_Early', 'opt_Early_Strength_Days', 'opt_Fineness'];
    
    function formatVal(val) {
        if (val === null || val === undefined || val === '') return '';
        const num = parseFloat(val);
        if (isNaN(num)) return val;
        return parseFloat(num.toFixed(2));
    }

    function populateOptimizer(data) {
        document.getElementById('opt_CaO').value = formatVal(data.CaO);
        document.getElementById('opt_SiO2').value = formatVal(data.SiO2);
        document.getElementById('opt_Al2O3').value = formatVal(data.Al2O3);
        document.getElementById('opt_Fe2O3').value = formatVal(data.Fe2O3);
        document.getElementById('opt_MgO').value = formatVal(data.MgO);
        document.getElementById('opt_SO3').value = formatVal(data.SO3);
        document.getElementById('opt_Strength_Early').value = formatVal(data.Strength_Early);
        document.getElementById('opt_Early_Strength_Days').value = formatVal(data.Early_Strength_Days) || '2';
        document.getElementById('opt_Fineness').value = formatVal(data.Fineness);
        runOptimizationSimulation();
    };

    async function runOptimizationSimulation() {
        const cType = cTypeSelect.value;
        const CaOVal = document.getElementById('opt_CaO').value;
        const SiO2Val = document.getElementById('opt_SiO2').value;
        const Al2O3Val = document.getElementById('opt_Al2O3').value;
        const Fe2O3Val = document.getElementById('opt_Fe2O3').value;

        // If core inputs are empty, don't run simulation
        if (!CaOVal && !SiO2Val && !Al2O3Val && !Fe2O3Val) {
            document.getElementById('opt_res_C3S').innerText = '--';
            document.getElementById('opt_res_C2S').innerText = '--';
            document.getElementById('opt_res_C3A').innerText = '--';
            document.getElementById('opt_res_C4AF').innerText = '--';
            document.getElementById('opt_res_LSF').innerText = '--';
            document.getElementById('opt_res_SM').innerText = '--';
            document.getElementById('opt_res_AM').innerText = '--';
            document.getElementById('opt_res_strength').innerText = '--';
            const adviceEl = document.getElementById('opt_advice');
            if (adviceEl) {
                adviceEl.innerHTML = 'Load a historical record above to start simulating and receiving AI advice...';
            }
            return;
        }

        const CaO = parseFloat(CaOVal) || 0;
        const SiO2 = parseFloat(SiO2Val) || 0;
        const Al2O3 = parseFloat(Al2O3Val) || 0;
        const Fe2O3 = parseFloat(Fe2O3Val) || 0;
        const MgO = parseFloat(document.getElementById('opt_MgO').value) || 0;
        const SO3 = parseFloat(document.getElementById('opt_SO3').value) || 0;
        const Strength_Early = parseFloat(document.getElementById('opt_Strength_Early').value) || 0;
        const Early_Strength_Days = parseFloat(document.getElementById('opt_Early_Strength_Days').value) || 2;
        const Fineness = parseFloat(document.getElementById('opt_Fineness').value) || 0;

        try {
            const chemRes = await fetch('/api/chemistry/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ SiO2, Al2O3, Fe2O3, CaO, MgO, SO3 })
            });
            const chem = await chemRes.json();

            document.getElementById('opt_res_C3S').innerText = chem.phases.C3S.toFixed(2);
            document.getElementById('opt_res_C2S').innerText = chem.phases.C2S.toFixed(2);
            document.getElementById('opt_res_C3A').innerText = chem.phases.C3A.toFixed(2);
            document.getElementById('opt_res_C4AF').innerText = chem.phases.C4AF.toFixed(2);
            document.getElementById('opt_res_LSF').innerText = chem.moduli.LSF.toFixed(2);
            document.getElementById('opt_res_SM').innerText = chem.moduli.SM.toFixed(2);
            document.getElementById('opt_res_AM').innerText = chem.moduli.AM.toFixed(2);

            const modelMeta = dashboardData.ml[cType];
            const reqData = {
                Cement_Type: cType,
                SiO2, Al2O3, Fe2O3, CaO, MgO, SO3,
                Strength_Early, Early_Strength_Days, Fineness
            };

            let strengthHtml = '--';
            let advice = `<strong>Chemistry Engine:</strong><br>${chem.advice}`;

            if (modelMeta.hasModel && modelMeta.confidence !== 'chemistry_only') {
                const res = await fetch('/api/predict', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(reqData)
                });
                const result = await res.json();
                if (result.prediction !== undefined) {
                    strengthHtml = `${result.prediction.toFixed(1)} <span style="font-size: 1.2rem; color: #94a3b8;">MPa</span>`;
                    advice += `<br><br><strong>${result.confidenceLabel}</strong> (R² ${(result.r2 * 100).toFixed(0)}%)`;
                }
            } else {
                strengthHtml = `<span style="font-size:0.95rem;color:#94a3b8;">ML not used — ${modelMeta.confidenceLabel}</span>`;
            }

            document.getElementById('opt_res_strength').innerHTML = strengthHtml;
            document.getElementById('opt_advice').innerHTML = advice;
        } catch (e) {
            console.error(e);
        }
    }

    optInputs.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', runOptimizationSimulation);
    });
}

// Populate lowest 28-day strength days
function populateLowStrengthDays() {
    const tbody = document.querySelector('#anomalyTable tbody');
    tbody.innerHTML = '';
    const rows = dashboardData.lowStrengthDays || dashboardData.anomalies || [];
    
    rows.forEach((a, i) => {
        const tr = document.createElement('tr');
        tr.style.animation = `fadeInUp 0.5s ease-out ${i * 0.08}s forwards`;
        tr.style.opacity = '0';
        
        // Color coding for low strength value
        const strVal = a.Strength;
        const color = strVal < 35 ? '#ef4444' : '#f59e0b';
        
        tr.innerHTML = `
            <td>${a.Date}</td>
            <td><span style="background: rgba(255,255,255,0.06); padding: 2px 6px; border-radius: 4px; font-size: 0.8rem;">${a.Type}</span></td>
            <td style="color: ${color}; font-weight: 700;">${strVal}</td>
            <td>${a.C3S}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Cement Type Distribution Chart (Doughnut)
function initDistributionChart() {
    const ctx = document.getElementById('distributionChart').getContext('2d');
    const distData = dashboardData.distribution;
    const labels = Object.keys(distData);
    const data = Object.values(distData);
    
    // Assign colors dynamically based on label
    const bgColors = labels.map(label => {
        if(label === 'OPC') return 'rgba(56, 189, 248, 0.8)';
        if(label === 'SRC') return 'rgba(16, 185, 129, 0.8)';
        if(label === 'SBC') return 'rgba(139, 92, 246, 0.8)';
        return 'rgba(255, 255, 255, 0.3)'; // Fallback
    });
    const borderColors = labels.map(label => {
        if(label === 'OPC') return '#38bdf8';
        if(label === 'SRC') return '#10b981';
        if(label === 'SBC') return '#8b5cf6';
        return '#ffffff';
    });

    distributionChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: bgColors,
                borderColor: borderColors,
                borderWidth: 1,
                hoverOffset: 10
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: '#94a3b8', font: { family: "'Outfit', sans-serif" } } },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    titleFont: { family: "'Outfit', sans-serif" },
                    bodyFont: { family: "'Outfit', sans-serif" }
                }
            },
            cutout: '70%'
        }
    });
}

// Feature Importance Chart (Bar)
function initImportanceChart(cType) {
    const ctx = document.getElementById('importanceChart').getContext('2d');
    const importances = dashboardData.ml[cType].importances;
    
    // Sort features by importance (descending)
    const sortedFeatures = Object.keys(importances).sort((a, b) => importances[b] - importances[a]);
    const labels = sortedFeatures.map(f => f.replace('_', ' '));
    const data = sortedFeatures.map(f => (importances[f] * 100).toFixed(2));

    importanceChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Importance (%)',
                data: data,
                backgroundColor: 'rgba(56, 189, 248, 0.5)',
                borderColor: '#38bdf8',
                borderWidth: 1,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.95)',
                    titleFont: { family: "'Outfit', sans-serif" },
                    bodyFont: { family: "'Outfit', sans-serif" },
                    callbacks: {
                        label: function(context) {
                            return context.parsed.y + '%';
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: { color: 'rgba(255, 255, 255, 0.03)', drawBorder: false },
                    ticks: { color: '#94a3b8' },
                    title: { display: true, text: 'Importance (%)', color: '#94a3b8' }
                },
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { color: '#94a3b8', maxRotation: 45, minRotation: 45 }
                }
            }
        }
    });
    
    document.getElementById('importanceDesc').innerText = `Relative influence of parameters for ${cType} strength prediction.`;
}

function updateImportanceChart(cType) {
    if (!importanceChart) return;
    const importances = dashboardData.ml[cType].importances;
    const sortedFeatures = Object.keys(importances).sort((a, b) => importances[b] - importances[a]);
    const labels = sortedFeatures.map(f => f.replace('_', ' '));
    const data = sortedFeatures.map(f => (importances[f] * 100).toFixed(2));
    
    importanceChart.data.labels = labels;
    importanceChart.data.datasets[0].data = data;
    
    // Change color based on cType
    let color = 'rgba(56, 189, 248, 0.5)';
    let border = '#38bdf8';
    if(cType === 'SRC') { color = 'rgba(16, 185, 129, 0.5)'; border = '#10b981'; }
    else if(cType === 'SBC') { color = 'rgba(139, 92, 246, 0.5)'; border = '#8b5cf6'; }
    
    importanceChart.data.datasets[0].backgroundColor = color;
    importanceChart.data.datasets[0].borderColor = border;
    
    importanceChart.update();
    document.getElementById('importanceDesc').innerText = `Relative influence of parameters for ${cType} strength prediction.`;
}

// Monthly Analysis Chart
function setupMonthlyChart() {
    const yearSelect = document.getElementById('monthlyYear');
    const monthSelect = document.getElementById('monthlyMonth');
    const paramSelect = document.getElementById('monthlyParam');

    // Populate years
    yearSelect.innerHTML = '';
    dashboardData.trends.labels.forEach(year => {
        const opt = document.createElement('option');
        opt.value = year;
        opt.innerText = year;
        yearSelect.appendChild(opt);
    });
    
    // Set default to the latest year and latest month with data
    if (dashboardData.latestDataMonth && dashboardData.latestDataMonth.year) {
        const latestYear = String(dashboardData.latestDataMonth.year);
        const latestMonth = String(dashboardData.latestDataMonth.month);
        // Set year if it exists in the options
        if ([...yearSelect.options].some(o => o.value === latestYear)) {
            yearSelect.value = latestYear;
        } else if (dashboardData.trends.labels.length > 0) {
            yearSelect.value = dashboardData.trends.labels[dashboardData.trends.labels.length - 1];
        }
        monthSelect.value = latestMonth;
    } else if (dashboardData.trends.labels.length > 0) {
        yearSelect.value = dashboardData.trends.labels[dashboardData.trends.labels.length - 1];
        monthSelect.value = "1";
    }

    // Listeners
    const handleChange = () => fetchAndRenderMonthlyChart();
    yearSelect.addEventListener('change', handleChange);
    monthSelect.addEventListener('change', handleChange);
    paramSelect.addEventListener('change', handleChange);

    // Initial load
    fetchAndRenderMonthlyChart();
}

async function fetchAndRenderMonthlyChart() {
    const year = document.getElementById('monthlyYear').value;
    const month = document.getElementById('monthlyMonth').value;
    const param = document.getElementById('monthlyParam').value;
    
    if (!year || !month || !param) return;

    try {
        const res = await fetch(`/api/monthly?year=${year}&month=${month}&param=${param}`);
        if (!res.ok) throw new Error('Failed to fetch monthly data');
        const data = await res.json();
        
        renderMonthlyChart(data, param);
    } catch (err) {
        console.error(err);
    }
}

function renderMonthlyChart(data, param) {
    const ctx = document.getElementById('monthlyChart').getContext('2d');
    
    const datasets = ['OPC', 'SRC', 'SBC'].map(c => ({
        label: c,
        data: data[c],
        borderColor: CEMENT_COLORS[c].border,
        backgroundColor: CEMENT_COLORS[c].bg,
        borderWidth: 2,
        tension: 0.2,
        fill: c === 'OPC',
        borderDash: c === 'OPC' ? [] : [5, 5],
        pointRadius: 4,
        spanGaps: true
    }));

    if (monthlyChart) {
        monthlyChart.data.labels = data.labels;
        monthlyChart.data.datasets = datasets;
        monthlyChart.options.scales.y.title.text = getParamUnit(param);
        monthlyChart.update();
    } else {
        monthlyChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { position: 'top', labels: { usePointStyle: true, pointStyle: 'circle' } },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.95)',
                        titleFont: { family: "'Outfit', sans-serif" },
                        bodyFont: { family: "'Outfit', sans-serif" },
                        callbacks: {
                            title: (context) => `Day ${context[0].label}`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.03)', drawBorder: false },
                        title: { display: true, text: 'Day of Month', color: '#94a3b8' }
                    },
                    y: {
                        grid: { color: 'rgba(255, 255, 255, 0.03)', drawBorder: false },
                        title: { display: true, text: getParamUnit(param), color: '#94a3b8' }
                    }
                },
                interaction: { mode: 'index', intersect: false }
            }
        });
    }
}

// Tab Switching Logic
window.switchTab = function(tabName) {
    const tabAnalytics = document.getElementById('tabAnalytics');
    const tabAI = document.getElementById('tabAI');
    const tabRawMix = document.getElementById('tabRawMix');
    
    const btnAnalytics = document.getElementById('tabBtnAnalytics');
    const btnAI = document.getElementById('tabBtnAI');
    const btnRawMix = document.getElementById('tabBtnRawMix');

    const activeStyle = "flex: 1; margin: 0; background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%); box-shadow: 0 4px 15px rgba(56, 189, 248, 0.3);";
    const inactiveStyle = "flex: 1; margin: 0; background: rgba(30, 41, 59, 0.8); border: 1px solid var(--glass-border); box-shadow: none;";

    if (tabName === 'analytics') {
        tabAnalytics.style.display = 'block';
        tabAI.style.display = 'none';
        tabRawMix.style.display = 'none';
        
        btnAnalytics.style = activeStyle;
        btnAI.style = inactiveStyle;
        btnRawMix.style = inactiveStyle;
    } else if (tabName === 'ai') {
        tabAnalytics.style.display = 'none';
        tabAI.style.display = 'block';
        tabRawMix.style.display = 'none';
        
        btnAnalytics.style = inactiveStyle;
        btnAI.style = activeStyle;
        btnRawMix.style = inactiveStyle;
    } else if (tabName === 'rawmix') {
        tabAnalytics.style.display = 'none';
        tabAI.style.display = 'none';
        tabRawMix.style.display = 'block';
        
        btnAnalytics.style = inactiveStyle;
        btnAI.style = inactiveStyle;
        btnRawMix.style = activeStyle;
    }
};

// FLS proportioning — server-side via /api/rawmix/calculate
async function calculateRawMixProportions() {
    const resultsBlock = document.getElementById('rawmix_results_block');
    const proportionsBlock = document.getElementById('rawmix_proportions_block');
    const promptBlock = document.getElementById('rawmix_prompt_block');

    const materials = {
        limestone: {
            SiO2: parseFloat(document.getElementById('raw_ls_SiO2').value),
            Al2O3: parseFloat(document.getElementById('raw_ls_Al2O3').value),
            Fe2O3: parseFloat(document.getElementById('raw_ls_Fe2O3').value),
            CaO: parseFloat(document.getElementById('raw_ls_CaO').value),
            MgO: parseFloat(document.getElementById('raw_ls_MgO').value),
            Na2O: parseFloat(document.getElementById('raw_ls_Na2O').value),
            K2O: parseFloat(document.getElementById('raw_ls_K2O').value),
            SO3: parseFloat(document.getElementById('raw_ls_SO3').value),
            LOI: parseFloat(document.getElementById('raw_ls_LOI').value),
            H2O: parseFloat(document.getElementById('raw_ls_H2O').value)
        },
        shale: {
            SiO2: parseFloat(document.getElementById('raw_sh_SiO2').value),
            Al2O3: parseFloat(document.getElementById('raw_sh_Al2O3').value),
            Fe2O3: parseFloat(document.getElementById('raw_sh_Fe2O3').value),
            CaO: parseFloat(document.getElementById('raw_sh_CaO').value),
            MgO: parseFloat(document.getElementById('raw_sh_MgO').value),
            Na2O: parseFloat(document.getElementById('raw_sh_Na2O').value),
            K2O: parseFloat(document.getElementById('raw_sh_K2O').value),
            SO3: parseFloat(document.getElementById('raw_sh_SO3').value),
            LOI: parseFloat(document.getElementById('raw_sh_LOI').value),
            H2O: parseFloat(document.getElementById('raw_sh_H2O').value)
        },
        sand: {
            SiO2: parseFloat(document.getElementById('raw_sd_SiO2').value),
            Al2O3: parseFloat(document.getElementById('raw_sd_Al2O3').value),
            Fe2O3: parseFloat(document.getElementById('raw_sd_Fe2O3').value),
            CaO: parseFloat(document.getElementById('raw_sd_CaO').value),
            MgO: parseFloat(document.getElementById('raw_sd_MgO').value),
            Na2O: parseFloat(document.getElementById('raw_sd_Na2O').value),
            K2O: parseFloat(document.getElementById('raw_sd_K2O').value),
            SO3: parseFloat(document.getElementById('raw_sd_SO3').value),
            LOI: parseFloat(document.getElementById('raw_sd_LOI').value),
            H2O: parseFloat(document.getElementById('raw_sd_H2O').value)
        },
        pyrite: {
            SiO2: parseFloat(document.getElementById('raw_py_SiO2').value),
            Al2O3: parseFloat(document.getElementById('raw_py_Al2O3').value),
            Fe2O3: parseFloat(document.getElementById('raw_py_Fe2O3').value),
            CaO: parseFloat(document.getElementById('raw_py_CaO').value),
            MgO: parseFloat(document.getElementById('raw_py_MgO').value),
            Na2O: parseFloat(document.getElementById('raw_py_Na2O').value),
            K2O: parseFloat(document.getElementById('raw_py_K2O').value),
            SO3: parseFloat(document.getElementById('raw_py_SO3').value),
            LOI: parseFloat(document.getElementById('raw_py_LOI').value),
            H2O: parseFloat(document.getElementById('raw_py_H2O').value)
        }
    };

    for (const [name, comp] of Object.entries(materials)) {
        for (const [oxide, val] of Object.entries(comp)) {
            if (isNaN(val)) {
                alert(`Please enter a valid numerical value for ${name} ${oxide}.`);
                return;
            }
        }
    }

    const payload = {
        mode: rawMixMode,
        cement_type: document.getElementById('raw_cement_type').value,
        materials,
        hfo: {
            heat: parseFloat(document.getElementById('raw_hfo_heat').value),
            calorific: parseFloat(document.getElementById('raw_hfo_cal').value),
            sulfur: parseFloat(document.getElementById('raw_hfo_sulfur').value)
        }
    };

    if (rawMixMode === 'solve') {
        payload.targets = {
            LSF: parseFloat(document.getElementById('raw_target_LSF').value),
            SM: parseFloat(document.getElementById('raw_target_SM').value),
            AM: parseFloat(document.getElementById('raw_target_AM').value)
        };
    } else {
        payload.recipe = {
            limestone: parseFloat(document.getElementById('raw_recipe_ls').value),
            shale: parseFloat(document.getElementById('raw_recipe_sh').value),
            sand: parseFloat(document.getElementById('raw_recipe_sd').value),
            pyrite: parseFloat(document.getElementById('raw_recipe_py').value)
        };
    }

    try {
        const res = await fetch('/api/rawmix/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            alert(data.detail || 'Calculation failed.');
            return;
        }

        document.getElementById('raw_result_dry').innerHTML = Object.entries(data.dry_proportions)
            .map(([k, v]) => `<li><span style="display:inline-block; width:120px;">${k}:</span> <strong>${v}%</strong></li>`)
            .join('');

        document.getElementById('raw_result_wet').innerHTML = Object.entries(data.wet_proportions)
            .map(([k, v]) => `<li><span style="display:inline-block; width:120px; color:#fff;">${k}:</span> <strong>${v}%</strong></li>`)
            .join('');

        const cl = data.clinker;
        document.getElementById('cl_SiO2').innerText = cl.SiO2;
        document.getElementById('cl_Al2O3').innerText = cl.Al2O3;
        document.getElementById('cl_Fe2O3').innerText = cl.Fe2O3;
        document.getElementById('cl_CaO').innerText = cl.CaO;
        document.getElementById('cl_MgO').innerText = cl.MgO;
        document.getElementById('cl_Na2O').innerText = cl.Na2O;
        document.getElementById('cl_K2O').innerText = cl.K2O;
        document.getElementById('cl_SO3').innerText = cl.SO3;
        document.getElementById('cl_LSF').innerText = cl.LSF;
        document.getElementById('cl_SM').innerText = cl.SM;
        document.getElementById('cl_AM').innerText = cl.AM;

        const ph = data.phases;
        document.getElementById('cl_C3S').innerText = `${ph.C3S}%`;
        document.getElementById('cl_C2S').innerText = `${ph.C2S}%`;
        document.getElementById('cl_C3A').innerText = `${ph.C3A}%`;
        document.getElementById('cl_C4AF').innerText = `${ph.C4AF}%`;

        const adviceContainer = document.getElementById('raw_diagnostic_advice');
        const diags = data.diagnostics || [];

        if (diags.length > 0) {
            const hasError = diags.some(d => d.severity === 'error');
            adviceContainer.style = hasError
                ? 'margin-top: 1.2rem; padding: 1rem; background: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; border-radius: 4px; font-size: 0.9rem; line-height: 1.5; color: #e2e8f0; text-align: left;'
                : 'margin-top: 1.2rem; padding: 1rem; background: rgba(245, 158, 11, 0.1); border-left: 4px solid #f59e0b; border-radius: 4px; font-size: 0.9rem; line-height: 1.5; color: #e2e8f0; text-align: left;';
            adviceContainer.innerHTML = diags.map(d => `<p style="margin-bottom:0.5rem;"><strong>${d.severity === 'error' ? '🚨' : '⚠️'}</strong> ${d.message}</p>`).join('');
        } else {
            adviceContainer.style = 'margin-top: 1.2rem; padding: 1rem; background: rgba(16, 185, 129, 0.1); border-left: 4px solid #10b981; border-radius: 4px; font-size: 0.9rem; line-height: 1.5; color: #e2e8f0; text-align: left;';
            adviceContainer.innerHTML = `<p><strong>✅ Optimal Sintering Design:</strong> Moduli targets satisfied (Liquid content: ${data.liquid_content}%, C₃A: ${ph.C3A}%).</p>`;
        }

        if (resultsBlock) resultsBlock.style.display = 'block';
        if (proportionsBlock) proportionsBlock.style.display = 'block';
        if (promptBlock) promptBlock.style.display = 'none';
    } catch (err) {
        console.error('Calculation error:', err);
        alert('An error occurred during calculations. Check console for details.');
    }
}
const rawMixCorrections = {
    OPC: { SiO2: 23.60, Al2O3: 8.25, Fe2O3: 27.69, CaO: 32.15, MgO: 5.93, Na2O: 0.20, K2O: 0.50, SO3: 1.50, LOI: 0.90, H2O: 6.5 },
    SBC: { SiO2: 23.60, Al2O3: 8.25, Fe2O3: 27.69, CaO: 32.15, MgO: 5.93, Na2O: 0.20, K2O: 0.50, SO3: 1.50, LOI: 0.90, H2O: 6.5 },
    SRC: { SiO2: 49.00, Al2O3: 0.69, Fe2O3: 37.18, CaO: 1.00, MgO: 0.90, Na2O: 0.29, K2O: 0.81, SO3: 1.50, LOI: 8.55, H2O: 7.8 }
};
let rawCementType = 'OPC';
let rawMixMode = 'solve';

// Setup and event wiring for Raw Mix tab
function setupRawMixCalculator() {
    const btnCalculate = document.getElementById('btnCalculateRawMix');
    const btnSolve = document.getElementById('raw_mode_solve');
    const btnCalc = document.getElementById('raw_mode_calc');
    const selectType = document.getElementById('raw_cement_type');

    if (btnCalculate) {
        btnCalculate.addEventListener('click', calculateRawMixProportions);
    }

    if (selectType) {
        selectType.addEventListener('change', (e) => {
            // Save current inputs to rawMixCorrections[rawCementType]
            rawMixCorrections[rawCementType] = {
                SiO2: parseFloat(document.getElementById('raw_py_SiO2').value) || 0,
                Al2O3: parseFloat(document.getElementById('raw_py_Al2O3').value) || 0,
                Fe2O3: parseFloat(document.getElementById('raw_py_Fe2O3').value) || 0,
                CaO: parseFloat(document.getElementById('raw_py_CaO').value) || 0,
                MgO: parseFloat(document.getElementById('raw_py_MgO').value) || 0,
                Na2O: parseFloat(document.getElementById('raw_py_Na2O').value) || 0,
                K2O: parseFloat(document.getElementById('raw_py_K2O').value) || 0,
                SO3: parseFloat(document.getElementById('raw_py_SO3').value) || 0,
                LOI: parseFloat(document.getElementById('raw_py_LOI').value) || 0,
                H2O: parseFloat(document.getElementById('raw_py_H2O').value) || 0
            };

            // Switch to new type
            rawCementType = e.target.value;
            const newChem = rawMixCorrections[rawCementType];
            const isSlag = (rawCementType === 'OPC' || rawCementType === 'SBC');
            const labelText = isSlag ? '4. Slag' : '4. Iron Ore';
            const recipeLabelText = isSlag ? 'Slag %' : 'Iron Ore %';

            // Update UI Labels
            document.getElementById('raw_material_4_label').innerText = labelText;
            document.getElementById('raw_recipe_py_label').innerText = recipeLabelText;

            // Load new chemistry values into inputs
            document.getElementById('raw_py_SiO2').value = newChem.SiO2.toFixed(2);
            document.getElementById('raw_py_Al2O3').value = newChem.Al2O3.toFixed(2);
            document.getElementById('raw_py_Fe2O3').value = newChem.Fe2O3.toFixed(2);
            document.getElementById('raw_py_CaO').value = newChem.CaO.toFixed(2);
            document.getElementById('raw_py_MgO').value = newChem.MgO.toFixed(2);
            document.getElementById('raw_py_Na2O').value = newChem.Na2O.toFixed(2);
            document.getElementById('raw_py_K2O').value = newChem.K2O.toFixed(2);
            document.getElementById('raw_py_SO3').value = newChem.SO3.toFixed(2);
            document.getElementById('raw_py_LOI').value = newChem.LOI.toFixed(2);
            document.getElementById('raw_py_H2O').value = newChem.H2O.toFixed(1);

            // Clear output
            document.getElementById('rawmix_results_block').style.display = 'none';
            document.getElementById('rawmix_proportions_block').style.display = 'none';
            document.getElementById('rawmix_prompt_block').style.display = 'block';
        });
    }

    if (btnSolve && btnCalc) {
        btnSolve.addEventListener('click', () => {
            rawMixMode = 'solve';
            btnSolve.style.background = 'linear-gradient(135deg, #38bdf8 0%, #0284c7 100%)';
            btnSolve.style.color = '#fff';
            btnSolve.style.border = 'none';
            btnSolve.style.boxShadow = '0 4px 15px rgba(56, 189, 248, 0.3)';
            
            btnCalc.style.background = 'rgba(30, 41, 59, 0.8)';
            btnCalc.style.color = 'var(--text-secondary)';
            btnCalc.style.border = '1px solid var(--glass-border)';
            btnCalc.style.boxShadow = 'none';

            document.getElementById('rawmix_target_moduli_block').style.display = 'block';
            document.getElementById('rawmix_recipe_input_block').style.display = 'none';
            btnCalculate.innerText = 'Calculate Feeder Proportions';
            document.getElementById('rawmix_results_title').innerText = 'Calculated Proportions & Clinker Chemistry';
            
            // Clear outputs
            document.getElementById('rawmix_results_block').style.display = 'none';
            document.getElementById('rawmix_proportions_block').style.display = 'none';
            document.getElementById('rawmix_prompt_block').style.display = 'block';
        });

        btnCalc.addEventListener('click', () => {
            rawMixMode = 'calc';
            btnCalc.style.background = 'linear-gradient(135deg, #38bdf8 0%, #0284c7 100%)';
            btnCalc.style.color = '#fff';
            btnCalc.style.border = 'none';
            btnCalc.style.boxShadow = '0 4px 15px rgba(56, 189, 248, 0.3)';
            
            btnSolve.style.background = 'rgba(30, 41, 59, 0.8)';
            btnSolve.style.color = 'var(--text-secondary)';
            btnSolve.style.border = '1px solid var(--glass-border)';
            btnSolve.style.boxShadow = 'none';

            document.getElementById('rawmix_target_moduli_block').style.display = 'none';
            document.getElementById('rawmix_recipe_input_block').style.display = 'block';
            btnCalculate.innerText = 'Calculate Resulting Moduli';
            document.getElementById('rawmix_results_title').innerText = 'Recipe Evaluation & Expected Chemistry';
            
            // Clear outputs
            document.getElementById('rawmix_results_block').style.display = 'none';
            document.getElementById('rawmix_proportions_block').style.display = 'none';
            document.getElementById('rawmix_prompt_block').style.display = 'block';
        });
    }

    // Add Excel Paste Support for the table
    const table = document.querySelector('.rawmix-input-table');
    if (table) {
        // Call it immediately on load
        updateRawMixTotals();

        table.addEventListener('input', function(e) {
            if (e.target.tagName === 'INPUT') {
                updateRawMixTotals();
            }
        });

        table.addEventListener('paste', (e) => {
            const pastedData = (e.clipboardData || window.clipboardData).getData('text');
            if (!pastedData) return;
            
            // Allow default behavior if it's not a multi-cell paste (doesn't contain tabs/newlines)
            if (pastedData.indexOf('\t') === -1 && pastedData.indexOf('\n') === -1) {
                return;
            }

            e.preventDefault();

            const rows = pastedData.split(/\r?\n/).filter(row => row.trim().length > 0);
            if (rows.length === 0) return;

            const targetInput = e.target;
            if (targetInput.tagName !== 'INPUT') return;

            const targetTd = targetInput.closest('td');
            const targetTr = targetInput.closest('tr');
            if (!targetTd || !targetTr) return;

            const tbody = targetTr.closest('tbody');
            const trs = Array.from(tbody.querySelectorAll('tr'));
            const startRowIdx = trs.indexOf(targetTr);
            
            const tds = Array.from(targetTr.querySelectorAll('td'));
            const startColIdx = tds.indexOf(targetTd);

            for (let i = 0; i < rows.length; i++) {
                const tr = trs[startRowIdx + i];
                if (!tr) break;
                
                const cells = rows[i].split('\t');
                const rowTds = Array.from(tr.querySelectorAll('td'));
                
                for (let j = 0; j < cells.length; j++) {
                    const td = rowTds[startColIdx + j];
                    if (!td) break;
                    
                    const input = td.querySelector('input');
                    if (input && !input.disabled && !input.readOnly) {
                        // Allow floats formatted with commas (EU style)
                        const val = parseFloat(cells[j].trim().replace(',', '.'));
                        if (!isNaN(val)) {
                            input.value = val;
                        }
                    }
                }
            }
            // Update totals after paste is processed
            updateRawMixTotals();
        });
    }

    const recipeBlock = document.getElementById('rawmix_recipe_input_block');
    if (recipeBlock) {
        updateRecipeTotals();
        recipeBlock.addEventListener('input', function(e) {
            if (e.target.tagName === 'INPUT') {
                updateRecipeTotals();
            }
        });
    }
}

// Helper to sum all oxides + LOI for each material
function updateRawMixTotals() {
    const materials = ['ls', 'sh', 'sd', 'py'];
    const oxides = ['SiO2', 'Al2O3', 'Fe2O3', 'CaO', 'MgO', 'Na2O', 'K2O', 'SO3', 'LOI'];
    
    materials.forEach(mat => {
        let sum = 0;
        oxides.forEach(ox => {
            const el = document.getElementById(`raw_${mat}_${ox}`);
            if (el) {
                sum += parseFloat(el.value) || 0;
            }
        });
        
        const totalEl = document.getElementById(`total_${mat}`);
        if (totalEl) {
            totalEl.textContent = sum.toFixed(2);
            // Highlight if not close to 100
            if (Math.abs(sum - 100) > 2) {
                totalEl.style.color = '#ef4444'; // Red
            } else {
                totalEl.style.color = '#10b981'; // Green
            }
        }
    });
}

// Helper to sum recipe inputs
function updateRecipeTotals() {
    const ls = parseFloat(document.getElementById('raw_recipe_ls')?.value) || 0;
    const sh = parseFloat(document.getElementById('raw_recipe_sh')?.value) || 0;
    const sd = parseFloat(document.getElementById('raw_recipe_sd')?.value) || 0;
    const py = parseFloat(document.getElementById('raw_recipe_py')?.value) || 0;
    const sum = ls + sh + sd + py;
    const totalEl = document.getElementById('raw_recipe_total');
    if (totalEl) {
        totalEl.textContent = sum.toFixed(2) + '%';
        if (Math.abs(sum - 100) > 0.1) {
            totalEl.style.color = '#ef4444'; // Red
        } else {
            totalEl.style.color = '#10b981'; // Green
        }
    }
}
