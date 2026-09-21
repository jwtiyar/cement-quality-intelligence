let trendChart = null;
let monthlyChart = null;
let distributionChart = null;
let importanceChart = null;
let dashboardData = null;
let latestPredictionContext = null;

function themeToken(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function getCementChartColor(label) {
    if (label === 'OPC') return themeToken('--cement-opc') || '#48a994';
    if (label === 'SRC') return themeToken('--cement-src') || '#d49341';
    if (label === 'SBC') return themeToken('--cement-sbc') || '#5ea1c9';
    return themeToken('--text-secondary') || '#8e9fa2';
}

const CEMENT_COLORS = {
    get OPC() {
        return {
            border: themeToken('--cement-opc') || '#48a994',
            bg: themeToken('--accent-subtle') || 'rgba(72, 169, 148, 0.12)'
        };
    },
    get SRC() {
        return {
            border: themeToken('--cement-src') || '#d49341',
            bg: 'transparent'
        };
    },
    get SBC() {
        return {
            border: themeToken('--cement-sbc') || '#5ea1c9',
            bg: 'transparent'
        };
    }
};

const systemTheme = matchMedia('(prefers-color-scheme: dark)');

function resolvedTheme(preference) {
    return preference === 'system' ? (systemTheme.matches ? 'dark' : 'light') : preference;
}

function syncChartTheme() {
    if (typeof Chart === 'undefined') return;
    const text = themeToken('--chart-text') || themeToken('--text-secondary');
    const grid = themeToken('--chart-grid');
    const tooltip = themeToken('--chart-tooltip');
    Chart.defaults.color = text;
    Chart.defaults.borderColor = grid;

    if (trendChart && trendChart.data?.datasets) {
        if (trendChart.data.datasets[0]) {
            trendChart.data.datasets[0].borderColor = CEMENT_COLORS.OPC.border;
            trendChart.data.datasets[0].backgroundColor = CEMENT_COLORS.OPC.bg;
            trendChart.data.datasets[0].pointBackgroundColor = CEMENT_COLORS.OPC.border;
            trendChart.data.datasets[0].pointBorderColor = themeToken('--panel-bg');
        }
        if (trendChart.data.datasets[1]) {
            trendChart.data.datasets[1].borderColor = CEMENT_COLORS.SRC.border;
        }
        if (trendChart.data.datasets[2]) {
            trendChart.data.datasets[2].borderColor = CEMENT_COLORS.SBC.border;
        }
    }

    if (monthlyChart && monthlyChart.data?.datasets) {
        ['OPC', 'SRC', 'SBC'].forEach((c, idx) => {
            if (monthlyChart.data.datasets[idx]) {
                monthlyChart.data.datasets[idx].borderColor = CEMENT_COLORS[c].border;
                monthlyChart.data.datasets[idx].backgroundColor = CEMENT_COLORS[c].bg;
            }
        });
    }

    if (distributionChart && distributionChart.data?.datasets?.[0]) {
        const labels = distributionChart.data.labels || [];
        distributionChart.data.datasets[0].backgroundColor = labels.map(l => getCementChartColor(l));
        distributionChart.data.datasets[0].borderColor = labels.map(l => getCementChartColor(l));
    }

    if (importanceChart && importanceChart.data?.datasets?.[0]) {
        const cType = document.getElementById('predictCementType')?.value || 'OPC';
        importanceChart.data.datasets[0].borderColor = getCementChartColor(cType);
        importanceChart.data.datasets[0].backgroundColor = themeToken('--accent-subtle') || getCementChartColor(cType);
    }

    [trendChart, monthlyChart, distributionChart, importanceChart].filter(Boolean).forEach(chart => {
        const plugins = chart.options.plugins || {};
        if (plugins.legend?.labels) plugins.legend.labels.color = text;
        if (plugins.tooltip) plugins.tooltip.backgroundColor = tooltip;
        Object.values(chart.options.scales || {}).forEach(scale => {
            if (scale.grid?.display !== false) scale.grid.color = grid;
            if (scale.ticks) scale.ticks.color = text;
            if (scale.title) scale.title.color = text;
        });
        chart.update('none');
    });
}

function applyTheme(preference, persist = true) {
    document.documentElement.dataset.themeResolved = resolvedTheme(preference);
    if (persist) localStorage.setItem('cementTheme', preference);
    const selector = document.getElementById('themeSelector');
    if (selector) selector.value = preference;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.content = themeToken('--bg-canvas') || themeToken('--bg-color');
    syncChartTheme();
}

function applyPalette(palette, persist = true) {
    document.documentElement.dataset.palette = palette;
    if (persist) localStorage.setItem('cementPalette', palette);
    const selector = document.getElementById('paletteSelector');
    if (selector) selector.value = palette;
    syncChartTheme();
}

const savedPalette = localStorage.getItem('cementPalette') || 'portland';
applyPalette(savedPalette, false);
document.getElementById('paletteSelector')?.addEventListener('change', event => applyPalette(event.target.value));

const savedTheme = localStorage.getItem('cementTheme') || 'system';
applyTheme(savedTheme, false);
document.getElementById('themeSelector')?.addEventListener('change', event => applyTheme(event.target.value));
systemTheme.addEventListener('change', () => {
    if ((localStorage.getItem('cementTheme') || 'system') === 'system') applyTheme('system', false);
});

function showAppNotice(message, tone = 'info') {
    const notice = document.getElementById('appNotice');
    if (!notice) return;
    notice.textContent = message;
    notice.dataset.tone = tone;
    notice.hidden = false;
    notice.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

// Escape untrusted text before any innerHTML use (CSV values, AI output)
function escapeHtml(s) {
    return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function appendStatus(container, label, text, style = '') {
    const paragraph = document.createElement('p');
    paragraph.style = style;
    const strong = document.createElement('strong');
    strong.textContent = label;
    paragraph.append(strong, document.createTextNode(` ${text}`));
    container.appendChild(paragraph);
}

function setSafeRichText(container, html) {
    const source = new DOMParser().parseFromString(String(html), 'text/html');
    const allowedTags = new Set(['STRONG', 'UL', 'LI', 'BR', 'I']);
    const fragment = document.createDocumentFragment();

    function copySafeNodes(sourceNode, targetNode) {
        sourceNode.childNodes.forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                targetNode.appendChild(document.createTextNode(node.textContent));
            } else if (node.nodeType === Node.ELEMENT_NODE) {
                const nextTarget = allowedTags.has(node.tagName)
                    ? targetNode.appendChild(document.createElement(node.tagName.toLowerCase()))
                    : targetNode;
                copySafeNodes(node, nextTarget);
            }
        });
    }

    copySafeNodes(source.body, fragment);
    container.replaceChildren(fragment);
}

// FastAPI validation errors come back as detail: [{loc, msg, type}, ...] —
// flatten them into human-readable text instead of "[object Object]"
function formatApiError(detail) {
    if (Array.isArray(detail)) {
        return detail.map(e => {
            const loc = (e.loc || []).filter(p => p !== "body").join(".");
            return loc ? `${loc}: ${e.msg}` : e.msg;
        }).join("; ");
    }
    return detail;
}


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
            btnSync.textContent = 'Refreshing…';
            btnSync.disabled = true;
            try {
                const res = await fetch('/api/refresh', { method: 'POST' });
                if (res.ok) {
                    const data = await res.json();
                    btnSync.textContent = 'Data refreshed';
                    
                    if (data.new_records && data.new_records.length > 0) {
                        let msg = `Added ${data.new_records.length} daily reports.\n`;
                        const samples = data.new_records.slice(0, 10).map(r => `• ${r.date} (${r.type})`).join('\n');
                        msg += samples;
                        if (data.new_records.length > 10) msg += `\nAnd ${data.new_records.length - 10} more.`;
                        showAppNotice(msg, 'success');
                    } else {
                        showAppNotice('Data is current. No new daily reports were found.', 'success');
                    }
                    
                    window.location.reload();
                } else {
                    btnSync.textContent = 'Refresh failed';
                    showAppNotice('Could not refresh the dataset.', 'error');
                    setTimeout(() => { btnSync.innerHTML = originalText; btnSync.disabled = false; }, 2000);
                }
            } catch (e) {
                btnSync.textContent = 'Refresh failed';
                showAppNotice('Could not connect to the data service.', 'error');
                setTimeout(() => { btnSync.innerHTML = originalText; btnSync.disabled = false; }, 2000);
            }
        });
    }

    try {
        const response = await fetch('/api/data');
        if (!response.ok) throw new Error('API server returned error');
        dashboardData = await response.json();

        // 0. Update Header Freshness Badge
        const freshnessEl = document.getElementById('dataFreshnessText');
        const freshnessContainer = document.getElementById('dataFreshness');
        if (freshnessEl && dashboardData.dataset && dashboardData.dataset.freshness) {
            const f = dashboardData.dataset.freshness;
            const recDate = f.latestRecordDate || dashboardData.dataset.latestRecordDate;
            const status = f.refreshStatus || 'idle';
            const ver = (f.datasetVersion || '').substring(0, 7);

            if (status === 'failed') {
                freshnessEl.textContent = 'Data: Refresh Warning';
                if (freshnessContainer) {
                    freshnessContainer.className = 'freshness-badge is-warning';
                    freshnessContainer.title = f.refreshError ? `Refresh failed: ${f.refreshError}` : 'Data refresh warning';
                }
            } else if (recDate) {
                freshnessEl.textContent = `Data: ${recDate}${ver ? ' (v' + ver + ')' : ''}`;
                if (freshnessContainer) {
                    freshnessContainer.className = 'freshness-badge';
                    freshnessContainer.title = `Latest laboratory record: ${recDate}${ver ? ' | Version: ' + ver : ''}`;
                }
            } else {
                freshnessEl.textContent = 'Data: Active';
                if (freshnessContainer) freshnessContainer.className = 'freshness-badge';
            }
        }
        
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

        // Populate Anomaly Banner
        const anomalyBanner = document.getElementById('anomaly_banner');
        if (dashboardData.anomalies && dashboardData.anomalies.length > 0) {
            const textDiv = document.getElementById('anomaly_text');
            anomalyBanner.style.display = 'block';
            
            let msg = `The system automatically scanned all Excel sheets during startup and found <strong>${dashboardData.anomalies.length}</strong> suspiciously large or small numbers (likely typos):<br><br><ul style="margin: 0; padding-left: 1.5rem;">`;
            const samples = dashboardData.anomalies.slice(0, 5);
            samples.forEach(a => {
                msg += `<li style="margin-bottom: 0.3rem;"><strong>${escapeHtml(a.Date)} (${escapeHtml(a.Type)}):</strong> ${escapeHtml(a.Parameter)} is logged as <strong>${escapeHtml(a.Value)}</strong> (Normal range is ${escapeHtml(a.Expected)})</li>`;
            });
            msg += `</ul>`;
            if (dashboardData.anomalies.length > 5) {
                msg += `<br><em>...and ${dashboardData.anomalies.length - 5} more.</em>`;
            }
            msg += `<br>Please check these dates in your Excel sheets, fix the typos, and click <strong>"Sync Live Excel Data"</strong> to clear this warning.`;
            textDiv.innerHTML = msg;
        } else if (anomalyBanner) {
            anomalyBanner.style.display = 'none';
        }

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
        const warnColor = themeToken('--status-warning') || '#d49341';
        ctx.fillStyle = themeToken('--status-warning-bg') || 'rgba(212, 147, 65, 0.08)';
        ctx.fillRect(chart.chartArea.left, top, x - chart.chartArea.left, bottom - top);

        // Dashed vertical line
        ctx.beginPath();
        ctx.setLineDash([6, 4]);
        ctx.strokeStyle = warnColor;
        ctx.lineWidth = 1.5;
        ctx.moveTo(x, top);
        ctx.lineTo(x, bottom);
        ctx.stroke();

        // Label background
        const label = `28D data from ${eraYear} →`;
        ctx.setLineDash([]);
        ctx.font = "500 11px system-ui";
        const tw = ctx.measureText(label).width;
        const lx = x + 5;
        const ly = top + 14;
        ctx.fillStyle = themeToken('--chart-tooltip');
        ctx.beginPath();
        ctx.roundRect(lx - 3, ly - 11, tw + 8, 18, 4);
        ctx.fill();

        // Label text
        ctx.fillStyle = warnColor;
        ctx.textBaseline = 'top';
        ctx.fillText(label, lx + 1, ly - 9);

        // Left-side label: sparse zone
        const sparseLabel = '← 2-day strength';
        ctx.font = "400 10px system-ui";
        const sw = ctx.measureText(sparseLabel).width;
        const sx = Math.max(chart.chartArea.left + 4, x - sw - 8);
        ctx.fillStyle = themeToken('--chart-tooltip');
        ctx.beginPath();
        ctx.roundRect(sx - 3, ly - 11, sw + 8, 18, 4);
        ctx.fill();
        ctx.fillStyle = themeToken('--text-secondary');
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
    
    Chart.defaults.color = themeToken('--text-secondary');
    Chart.defaults.font.family = "system-ui";
    
    _eraLineActive = (param === 'Strength_28D') && !!dashboardData.strength28Era;

    const datasets = [
        {
            label: 'OPC (Ordinary Portland)', data: paramData.OPC,
            borderColor: CEMENT_COLORS.OPC.border, backgroundColor: CEMENT_COLORS.OPC.bg,
            borderWidth: 3, tension: 0.35, fill: true, spanGaps: false,
            pointBackgroundColor: CEMENT_COLORS.OPC.border,
            pointBorderColor: themeToken('--panel'), pointBorderWidth: 2, pointRadius: 5, pointHoverRadius: 7
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
                    backgroundColor: themeToken('--chart-tooltip'),
                    titleFont: { size: 13, family: "system-ui", weight: 'bold' },
                    bodyFont: { size: 12, family: "system-ui" },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: true
                }
            },
            scales: {
                x: {
                    grid: { color: themeToken('--chart-grid'), drawBorder: false }
                },
                y: {
                    grid: { color: themeToken('--chart-grid'), drawBorder: false },
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
        case 'Strength_Early': return '2-Day Strength (MPa)';
        case 'C3S': return 'Tricalcium Silicate (C3S %)';
        case 'CaO': return 'Lime (CaO %)';
        case 'Fineness': return 'Fineness / Blaine (cm²/g)';
        case 'LSF': return 'Lime Saturation Factor (LSF %)';
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
        subtitle.innerHTML = `⚠️ 28-day strength data becomes reliably available from <strong>${eraYear}</strong> onward. Earlier years have sparse 28D records (mostly 2-day tests only).`;
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
        bodyHTML += `<tr><td style="font-weight: 600; text-align: left; background: var(--panel-header); font-family: var(--font-sans);">${rowCol.replace('_', ' ')}</td>`;
        cols.forEach(colCol => {
            const val = matrix[rowCol][colCol] || 0;
            const style = getCorrelationStyle(val);
            bodyHTML += `<td style="background-color: ${style.bg}; color: ${style.color}; font-weight: 600; text-align: center;">${val.toFixed(2)}</td>`;
        });
        bodyHTML += '</tr>';
    });
    bodyHTML += '</tbody>';

    table.innerHTML = headerHTML + bodyHTML;
}

function getCorrelationStyle(val) {
    if (val === 1.0) {
        return {
            bg: 'var(--accent-subtle)',
            color: 'var(--accent)'
        };
    }
    const isLight = document.documentElement.dataset.themeResolved === 'light';
    if (val > 0) {
        const opacity = Math.min(Math.max(val * 0.7, 0.08), 0.85);
        const textColor = opacity > 0.45 ? '#ffffff' : (isLight ? '#12191a' : '#e6eded');
        return {
            bg: `rgba(217, 83, 79, ${opacity.toFixed(2)})`,
            color: textColor
        };
    } else {
        const opacity = Math.min(Math.max(Math.abs(val) * 0.7, 0.08), 0.85);
        const textColor = opacity > 0.45 ? '#ffffff' : (isLight ? '#12191a' : '#e6eded');
        return {
            bg: `rgba(94, 161, 201, ${opacity.toFixed(2)})`,
            color: textColor
        };
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
    
    let lastLoadedRecordDate = null;
    
    // Function to clear optimizer inputs and reset outputs
    function clearOptimizerInputs() {
        lastLoadedRecordDate = null;
        latestPredictionContext = null;
        document.getElementById('opt_CaO').value = '';
        document.getElementById('opt_SiO2').value = '';
        document.getElementById('opt_Al2O3').value = '';
        document.getElementById('opt_Fe2O3').value = '';
        document.getElementById('opt_MgO').value = '';
        document.getElementById('opt_SO3').value = '';
        document.getElementById('opt_Strength_Early').value = '';
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
            if (!res.ok) throw new Error(`Record lookup failed (${res.status})`);
            const resData = await res.json();

            if (resData.found) {
                lastLoadedRecordDate = dateVal;
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
            if (!res.ok) throw new Error(`Latest-date lookup failed (${res.status})`);
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
            showAppNotice('Select a date before loading a record.', 'error');
            return;
        }
        loadRecordForSelectedDateAndType();
    });

    // --- AI Mix Optimizer & Simulator Logic ---
    const optInputs = ['opt_CaO', 'opt_SiO2', 'opt_Al2O3', 'opt_Fe2O3', 'opt_MgO', 'opt_SO3', 'opt_Strength_Early', 'opt_Fineness'];
    
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
            document.getElementById('expectedDateBox').style.display = 'none';
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
        const Fineness = parseFloat(document.getElementById('opt_Fineness').value) || 0;

        try {
            const chemRes = await fetch('/api/chemistry/analyze', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ SiO2, Al2O3, Fe2O3, CaO, MgO, SO3 })
            });
            if (!chemRes.ok) throw new Error(`Chemistry analysis failed (${chemRes.status})`);
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
                Strength_Early, Fineness
            };

            let strengthHtml = '--';
            let advice = `<strong>Chemistry Engine:</strong><br>${chem.advice}`;

            if (modelMeta.hasModel) {
                const res = await fetch('/api/predict', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(reqData)
                });
                if (!res.ok) throw new Error(`Strength prediction failed (${res.status})`);
                const result = await res.json();
                if (result.prediction !== undefined) {
                    const decision = result.typesafe || {};
                    const normalizedReview = {
                        enabled: Boolean(decision.enabled),
                        safe_to_show: decision.safe_to_show !== undefined ? decision.safe_to_show : null,
                        probability: decision.probability !== undefined ? decision.probability : null,
                        status: decision.status || (decision.enabled ? (decision.safe_to_show ? "approved" : "rejected") : "not_reviewed")
                    };
                    latestPredictionContext = {
                        cement_type: cType,
                        prediction: result.prediction,
                        prediction_source: result.prediction_source || result.predictionSource || (result.confidence === 'chemistry_only' ? 'recent_mean' : 'xgboost'),
                        confidence: result.confidence,
                        confidence_label: result.confidenceLabel,
                        r2: result.r2,
                        rmse: result.rmse,
                        typesafe: normalizedReview
                    };
                    if (normalizedReview.status === 'rejected' || normalizedReview.safe_to_show === false) {
                        strengthHtml = `<span style="font-size:0.95rem;color:#f59e0b;">Held for qualified review — TypeSafe confidence ${(decision.probability * 100).toFixed(0)}%</span>`;
                        advice += `<br><br><strong>TypeSafe review required before using this estimate.</strong>`;
                        document.getElementById('expectedDateBox').style.display = 'none';
                    } else {
                        strengthHtml = `${result.prediction.toFixed(1)} <span style="font-size: 1.2rem; color: #94a3b8;">MPa</span>`;
                        advice += `<br><br><strong>${result.confidenceLabel}</strong>`;
                        if (result.predictionSource === 'recent_mean') {
                            advice += `<br>Historical XGBoost held back; recent validation favored this baseline.`;
                        } else {
                            advice += ` (R² ${(result.r2 * 100).toFixed(0)}%)`;
                        }
                        if (normalizedReview.status === 'approved') {
                            advice += `<br><strong>TypeSafe status:</strong> Approved (${(normalizedReview.probability * 100).toFixed(0)}%)`;
                        } else {
                            advice += `<br><span style="font-size:0.85rem;color:var(--text-secondary);">Safety review: Not reviewed</span>`;
                        }

                        const dateBox = document.getElementById('expectedDateBox');
                        const dateLabel = dateBox.querySelector('.label');
                        const dateVal = document.getElementById('expectedBreakDate');

                        let baseDateObj = new Date();
                        if (lastLoadedRecordDate) {
                            const parts = lastLoadedRecordDate.split('-');
                            if (parts.length === 3) {
                                baseDateObj = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
                            } else {
                                baseDateObj = new Date(lastLoadedRecordDate);
                            }
                        } else {
                            baseDateObj.setDate(baseDateObj.getDate() - 2);
                        }
                        baseDateObj.setDate(baseDateObj.getDate() + 28);

                        const options = { weekday: 'short', year: 'numeric', month: 'short', day: 'numeric' };
                        const hasActual = actualResultBox && actualResultBox.style.display !== 'none';

                        if (hasActual) {
                            dateLabel.innerText = 'Actual Break Date:';
                            dateVal.innerText = baseDateObj.toLocaleDateString(undefined, options);
                            dateBox.style.background = 'var(--status-info-bg)';
                            dateBox.style.borderColor = 'var(--status-info-border)';
                            dateVal.style.color = 'var(--status-info)';
                        } else if (baseDateObj < new Date()) {
                            dateLabel.innerText = '28-Day Test Status:';
                            dateVal.innerText = 'Unrecorded test';
                            dateBox.style.background = 'var(--status-warning-bg, #fef3c7)';
                            dateBox.style.borderColor = 'var(--status-warning-border, #f59e0b)';
                            dateVal.style.color = 'var(--status-warning, #b45309)';
                        } else {
                            dateLabel.innerText = 'Expected 28-Day Break Date:';
                            dateVal.innerText = baseDateObj.toLocaleDateString(undefined, options);
                            dateBox.style.background = 'var(--status-nominal-bg)';
                            dateBox.style.borderColor = 'var(--status-nominal-border)';
                            dateVal.style.color = 'var(--status-nominal)';
                        }
                        dateBox.style.display = 'flex';
                    }
                }
            } else {
                latestPredictionContext = null;
                strengthHtml = `<span style="font-size:0.95rem;color:#94a3b8;">ML not used — ${modelMeta.confidenceLabel}</span>`;
                document.getElementById('expectedDateBox').style.display = 'none';
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
        
        const strVal = a.Strength;
        const color = strVal < 35 ? 'var(--status-alarm)' : 'var(--status-warning)';
        const badgeType = (a.Type || 'opc').toLowerCase();
        
        tr.innerHTML = `
            <td>${escapeHtml(a.Date)}</td>
            <td><span class="cement-badge cement-badge-${badgeType}">${escapeHtml(a.Type)}</span></td>
            <td style="color: ${color}; font-weight: 700;">${escapeHtml(strVal)}</td>
            <td>${escapeHtml(a.C3S)}</td>
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
    
    const bgColors = labels.map(label => getCementChartColor(label));
    const borderColors = labels.map(label => getCementChartColor(label));

    distributionChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: bgColors,
                borderColor: borderColors,
                borderWidth: 1,
                hoverOffset: 6
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'right', labels: { color: themeToken('--text-secondary'), font: { family: "system-ui" } } },
                tooltip: {
                    backgroundColor: themeToken('--chart-tooltip'),
                    titleFont: { family: "system-ui" },
                    bodyFont: { family: "system-ui" }
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
    const border = getCementChartColor(cType);

    importanceChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Importance (%)',
                data: data,
                backgroundColor: themeToken('--accent-subtle') || border,
                borderColor: border,
                borderWidth: 1,
                borderRadius: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: themeToken('--chart-tooltip'),
                    titleFont: { family: "system-ui" },
                    bodyFont: { family: "system-ui" },
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
                    grid: { color: themeToken('--chart-grid'), drawBorder: false },
                    ticks: { color: themeToken('--text-secondary') },
                    title: { display: true, text: 'Importance (%)', color: themeToken('--text-secondary') }
                },
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { color: themeToken('--text-secondary'), maxRotation: 45, minRotation: 45 }
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
    
    const border = getCementChartColor(cType);
    importanceChart.data.datasets[0].backgroundColor = themeToken('--accent-subtle') || border;
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
                        backgroundColor: themeToken('--chart-tooltip'),
                        titleFont: { family: "system-ui" },
                        bodyFont: { family: "system-ui" },
                        callbacks: {
                            title: (context) => `Day ${context[0].label}`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: themeToken('--chart-grid'), drawBorder: false },
                        title: { display: true, text: 'Day of Month', color: themeToken('--text-secondary') }
                    },
                    y: {
                        grid: { color: themeToken('--chart-grid'), drawBorder: false },
                        title: { display: true, text: getParamUnit(param), color: themeToken('--text-secondary') }
                    }
                },
                interaction: { mode: 'index', intersect: false }
            }
        });
    }
}

const tabNames = ['analytics', 'ai', 'rawmix', 'chat'];
const tabElements = {
    analytics: ['tabAnalytics', 'tabBtnAnalytics'],
    ai: ['tabAI', 'tabBtnAI'],
    rawmix: ['tabRawMix', 'tabBtnRawMix'],
    chat: ['tabChat', 'tabBtnChat'],
};

window.switchTab = function(tabName, updateUrl = true) {
    const selected = tabNames.includes(tabName) ? tabName : 'analytics';

    tabNames.forEach(name => {
        const [panelId, buttonId] = tabElements[name];
        const panel = document.getElementById(panelId);
        const button = document.getElementById(buttonId);
        const active = name === selected;
        if (panel) panel.style.display = active ? 'block' : 'none';
        if (button) {
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-selected', String(active));
            button.tabIndex = active ? 0 : -1;
        }
    });

    if (updateUrl && window.location.hash !== `#${selected}`) {
        window.history.pushState({ tab: selected }, '', `#${selected}`);
    }
};

window.addEventListener('popstate', () => {
    window.switchTab(window.location.hash.slice(1), false);
});

window.switchTab(window.location.hash.slice(1) || 'analytics', false);

document.querySelector('.tabs-container')?.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const current = tabNames.findIndex(name => tabElements[name][1] === document.activeElement.id);
    const next = event.key === 'Home' ? 0
        : event.key === 'End' ? tabNames.length - 1
        : (current + (event.key === 'ArrowRight' ? 1 : -1) + tabNames.length) % tabNames.length;
    window.switchTab(tabNames[next]);
    document.getElementById(tabElements[tabNames[next]][1]).focus();
});

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
                showAppNotice(`Enter a valid number for ${name} ${oxide}.`, 'error');
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

    const extraFields = rawMixMode === 'solve'
        ? { LSF: 'raw_target_LSF', SM: 'raw_target_SM', AM: 'raw_target_AM' }
        : { limestone: 'raw_recipe_ls', shale: 'raw_recipe_sh', sand: 'raw_recipe_sd', pyrite: 'raw_recipe_py' };

    for (const [name, id] of Object.entries({
        'hfo heat': 'raw_hfo_heat',
        'hfo calorific': 'raw_hfo_cal',
        'hfo sulfur': 'raw_hfo_sulfur',
        ...extraFields,
    })) {
        const val = parseFloat(document.getElementById(id).value);
        if (isNaN(val)) {
            showAppNotice(`Enter a valid number for ${name}.`, 'error');
            return;
        }
    }

    try {
        const res = await fetch('/api/rawmix/calculate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) {
            showAppNotice(formatApiError(data.detail) || 'Calculation failed.', 'error');
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
        adviceContainer.replaceChildren();

        if (diags.length > 0) {
            const hasError = diags.some(d => d.severity === 'error');
            adviceContainer.className = 'advice-card';
            adviceContainer.dataset.tone = hasError ? 'alarm' : 'warning';
            adviceContainer.removeAttribute('style');
            diags.forEach(d => appendStatus(
                adviceContainer,
                d.severity === 'error' ? '🚨' : '⚠️',
                d.message,
                'margin-bottom:0.5rem;'
            ));
        } else {
            adviceContainer.className = 'advice-card';
            adviceContainer.dataset.tone = 'nominal';
            adviceContainer.removeAttribute('style');
            appendStatus(adviceContainer, '✅ Optimal Sintering Design:', `Moduli targets satisfied (Liquid content: ${data.liquid_content}%, C₃A: ${ph.C3A}%).`);
        }

        const typesafe = data.typesafe || {};
        if (typesafe.enabled) {
            const labels = {
                monitor: 'Monitor routine plant data',
                adjust_recipe: 'Adjust recipe or process targets',
                stop_and_review: 'Stop and request qualified review',
            };
            const action = typesafe.requires_human_review
                ? labels.stop_and_review
                : (labels[typesafe.action] || labels.stop_and_review);
            appendStatus(adviceContainer, 'TypeSafe review:', `${action} (${(typesafe.confidence * 100).toFixed(0)}% confidence).`, 'margin-top:0.7rem;');
            const probabilities = Object.entries(typesafe.probabilities || {})
                .map(([name, value]) => `${labels[name] || name}: ${(value * 100).toFixed(0)}%`)
                .join(' · ');
            appendStatus(
                adviceContainer,
                'Human-review probability:',
                `${(typesafe.review_probability * 100).toFixed(0)}%${probabilities ? `\n${probabilities}` : ''}`,
                'margin-top:0.35rem;color:var(--text-secondary);white-space:pre-line;'
            );
        }

        if (resultsBlock) resultsBlock.style.display = 'block';
        if (proportionsBlock) proportionsBlock.style.display = 'block';
        if (promptBlock && data.explanation) {
            promptBlock.className = 'advice-card';
            promptBlock.dataset.tone = 'info';
            promptBlock.style.display = 'block';
            promptBlock.style.marginTop = '1rem';
            setSafeRichText(promptBlock, data.explanation);
        } else if (promptBlock) {
            promptBlock.style.display = 'none';
        }
    } catch (err) {
        console.error('Calculation error:', err);
        showAppNotice('The calculation failed. Check the entered values and try again.', 'error');
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
            btnSolve.classList.add('is-active');
            btnCalc.classList.remove('is-active');

            document.getElementById('rawmix_target_moduli_block').style.display = 'block';
            document.getElementById('rawmix_recipe_input_block').style.display = 'none';
            btnCalculate.innerText = 'Calculate proportions';
            document.getElementById('rawmix_results_title').innerText = 'Raw-mix result';
            
            // Clear outputs
            document.getElementById('rawmix_results_block').style.display = 'none';
            document.getElementById('rawmix_proportions_block').style.display = 'none';
            document.getElementById('rawmix_prompt_block').style.display = 'block';
        });

        btnCalc.addEventListener('click', () => {
            rawMixMode = 'recipe';
            btnCalc.classList.add('is-active');
            btnSolve.classList.remove('is-active');

            document.getElementById('rawmix_target_moduli_block').style.display = 'none';
            document.getElementById('rawmix_recipe_input_block').style.display = 'block';
            btnCalculate.innerText = 'Check recipe';
            document.getElementById('rawmix_results_title').innerText = 'Recipe result';
            
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

// ==========================================
// AI Assistant & RAG Implementation
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    const chatHistory = document.getElementById("chatHistory");
    const chatInput = document.getElementById("chatInput");
    const btnSendChat = document.getElementById("btnSendChat");
    const btnClearChat = document.getElementById("btnClearChat");
    const btnRebuildRAG = document.getElementById("btnRebuildRAG");
    const ragStatus = document.getElementById("ragStatus");
    const citedSources = document.getElementById("citedSources");
    const aiProvider = document.getElementById("aiProvider");
    const activeModelLabel = document.getElementById("activeModelLabel");

    let history = [];

    const providerLabels = {
        gemini: "Gemini 3.8 Flash",
        codex: "gpt-5.6-luna (medium) — ChatGPT account",
    };
    const savedProvider = localStorage.getItem("cementAiProvider");
    if (aiProvider && providerLabels[savedProvider]) aiProvider.value = savedProvider;

    function updateProviderLabel(label, prefix = "Selected") {
        if (activeModelLabel) {
            activeModelLabel.textContent = `${prefix}: ${label || providerLabels[aiProvider?.value]}`;
        }
    }

    updateProviderLabel();
    if (aiProvider) {
        aiProvider.addEventListener("change", () => {
            localStorage.setItem("cementAiProvider", aiProvider.value);
            updateProviderLabel();
        });
    }

    // Clear history
    if (btnClearChat) {
        btnClearChat.addEventListener("click", () => {
            history = [];
            chatHistory.innerHTML = `
                <div class="chat-message model">
                    Ask about plant results or search the reference documents.
                </div>
            `;
            citedSources.innerHTML = `<div style="text-align: center; padding: 2rem 0; color: var(--text-muted);">Sources will appear after an answer cites a document.</div>`;
        });
    }

    // Append a message bubble to chat
    function appendMessage(role, text) {
        const bubble = document.createElement("div");
        bubble.className = `chat-message ${role}`;
        if (role === "user") {
            bubble.innerText = text;
        } else {
            // Render markdown-like formatting (bold, newlines) safely:
            // escape HTML first so AI-generated tags can never execute
            const escaped = escapeHtml(text);
            const formattedText = escaped
                .replace(/\n/g, "<br>")
                .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
            bubble.innerHTML = formattedText;
        }
        chatHistory.appendChild(bubble);
        chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    // Send Message
    async function sendMessage() {
        const query = chatInput.value.trim();
        if (!query) return;

        chatInput.value = "";
        appendMessage("user", query);
        const provider = aiProvider?.value || "gemini";
        btnSendChat.disabled = true;
        btnSendChat.textContent = "Send · Thinking…";

        // Show typing indicator
        const typingIndicator = document.createElement("div");
        typingIndicator.id = "typingIndicator";
        typingIndicator.className = "chat-message model typing";
        typingIndicator.innerText = "Thinking…";
        chatHistory.appendChild(typingIndicator);
        chatHistory.scrollTop = chatHistory.scrollHeight;

        try {
            const res = await fetch("/api/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    message: query,
                    history: history,
                    prediction_context: latestPredictionContext,
                    provider,
                })
            });

            // Remove typing indicator
            const ind = document.getElementById("typingIndicator");
            if (ind) ind.remove();

            if (!res.ok) {
                const errData = await res.json();
                appendMessage("model", `Error: ${errData.detail || `Could not reach ${providerLabels[provider]}`}`);
                return;
            }

            const data = await res.json();
            appendMessage("model", data.response);
            updateProviderLabel(data.model || providerLabels[provider], "Last response");

            // Update local history
            history.push({ role: "user", content: query });
            history.push({ role: "model", content: data.response });

            // Keep history window to latest 10 messages
            if (history.length > 20) {
                history = history.slice(history.length - 20);
            }

            // Update cited sources list on sidebar
            if (data.sources && data.sources.length > 0) {
                citedSources.innerHTML = "";
                data.sources.forEach(src => {
                    const item = document.createElement("div");
                    item.className = "source-item";
                    const typeSafeScore = Number.isFinite(src.typesafeScore)
                        ? `<span>TypeSafe: ${(src.typesafeScore * 100).toFixed(0)}%</span>`
                        : '';
                    item.innerHTML = `
                        <div style="font-weight:600; color:var(--text-primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(src.file)}">${escapeHtml(src.file)}</div>
                        <div style="display:flex; justify-content:space-between; font-size:0.75rem; margin-top:0.2rem; color:var(--text-secondary);">
                            <span>Page ${escapeHtml(src.page)}</span>
                            <span>TF-IDF: ${(src.score * 100).toFixed(0)}%</span>
                            ${typeSafeScore}
                        </div>
                    `;
                    citedSources.appendChild(item);
                });
            } else {
                citedSources.innerHTML = `<div style="text-align: center; padding: 2rem 0; color: var(--text-muted);">No sources cited for this query.</div>`;
            }

        } catch (err) {
            console.error(err);
            const ind = document.getElementById("typingIndicator");
            if (ind) ind.remove();
            appendMessage("model", "Error connecting to server.");
        } finally {
            btnSendChat.disabled = false;
            btnSendChat.textContent = "Send";
        }
    }

    if (btnSendChat) btnSendChat.addEventListener("click", sendMessage);
    if (chatInput) {
        chatInput.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
                sendMessage();
            }
        });
    }

    // Rebuild Vector Index
    if (btnRebuildRAG) {
        btnRebuildRAG.addEventListener("click", async () => {
            const originalText = btnRebuildRAG.innerText;
            btnRebuildRAG.disabled = true;
            btnRebuildRAG.innerText = "Updating index…";
            btnRebuildRAG.style.opacity = "0.7";
            ragStatus.innerHTML = `<strong style="color:var(--accent);">Reading reference documents…</strong>`;

            try {
                const res = await fetch("/api/rag/rebuild", { method: "POST" });
                if (res.ok) {
                    ragStatus.innerHTML = `<strong style="color:#69b88b;">Document index updated.</strong>`;
                    showAppNotice("Document index updated.", "success");
                } else {
                    const err = await res.json();
                    ragStatus.innerHTML = `<strong style="color:#e0716f;">Index update failed.</strong>`;
                    showAppNotice(`Index update failed: ${err.detail || 'Unknown error'}`, "error");
                }
            } catch (err) {
                console.error(err);
                ragStatus.innerHTML = `<strong style="color:#e0716f;">Could not connect to the document service.</strong>`;
                showAppNotice("Could not connect to the document service.", "error");
            } finally {
                btnRebuildRAG.disabled = false;
                btnRebuildRAG.innerText = originalText;
                btnRebuildRAG.style.opacity = "1";
            }
        });
    }
});
