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
            bg: themeToken('--accent-subtle') || 'rgba(72, 169, 148, 0.14)'
        };
    },
    get SRC() {
        return {
            border: themeToken('--cement-src') || '#d49341',
            bg: 'rgba(212, 147, 65, 0.16)'
        };
    },
    get SBC() {
        return {
            border: themeToken('--cement-sbc') || '#5ea1c9',
            bg: 'rgba(94, 161, 201, 0.16)'
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
        ['OPC', 'SRC', 'SBC'].forEach((c, idx) => {
            if (trendChart.data.datasets[idx]) {
                trendChart.data.datasets[idx].borderColor = CEMENT_COLORS[c].border;
                trendChart.data.datasets[idx].pointBackgroundColor = CEMENT_COLORS[c].border;
                trendChart.data.datasets[idx].pointBorderColor = themeToken('--panel-bg') || '#ffffff';
            }
        });
        if (typeof applyTrendFilterStyles === 'function') {
            applyTrendFilterStyles();
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
                let res = await fetch('/api/refresh', { method: 'POST' });
                if (!res.ok) {
                    const errData = await res.json().catch(() => ({}));
                    const detail = errData.detail || '';
                    if (detail.includes('allow_deletions=True') || detail.includes('changed or missing values')) {
                        const confirmed = confirm(
                            `Dataset notice:\n${detail}\n\nDo you want to force refresh and accept these changes?`
                        );
                        if (confirmed) {
                            btnSync.textContent = 'Force refreshing…';
                            res = await fetch('/api/refresh?allow_deletions=true', { method: 'POST' });
                        }
                    }
                }

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
                    
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    const errData = await res.json().catch(() => ({}));
                    btnSync.textContent = 'Refresh failed';
                    showAppNotice(errData.detail || 'Could not refresh the dataset.', 'error');
                    setTimeout(() => { btnSync.innerHTML = originalText; btnSync.disabled = false; }, 3000);
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
        
        // 1. Populate Summary Statistics & Period Controls
        if (dashboardData.averages) {
            setupPeriodAveragesControls(dashboardData.averages);
            renderSummaryCards(dashboardData.averages);
        } else if (dashboardData.summary) {
            renderSummaryCards({
                totalRecords: dashboardData.summary.totalRecords,
                avgStrength: dashboardData.summary.avgStrength,
                avgC3S: dashboardData.summary.avgC3S,
                yearsCoverage: dashboardData.summary.yearsCoverage,
                periodLabel: 'Full Dataset (All Time)',
                seasonalBreakdown: []
            });
        }

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
        setupTrendChartControls();

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

        let meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data || !meta.data[eraIndex] || meta.hidden) {
            for (let i = 1; i < (chart.data.datasets ? chart.data.datasets.length : 0); i++) {
                const candidate = chart.getDatasetMeta(i);
                if (candidate && candidate.data && candidate.data[eraIndex] && !candidate.hidden) {
                    meta = candidate;
                    break;
                }
            }
        }
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

// --- Trend Chart State & Functions ---
let currentTrendParam = 'Strength_28D';
let currentTrendFilter = 'all'; // 'all', 'OPC', 'SRC', 'SBC'
let trendOffsetActive = false;

function getTrendDisplayData(param) {
    if (!dashboardData || !dashboardData.trends || !dashboardData.trends.data) {
        return { OPC: [], SRC: [], SBC: [] };
    }
    const rawData = dashboardData.trends.data[param];
    if (!rawData) {
        return { OPC: [], SRC: [], SBC: [] };
    }
    if (!trendOffsetActive) {
        return {
            OPC: (rawData.OPC || []).slice(),
            SRC: (rawData.SRC || []).slice(),
            SBC: (rawData.SBC || []).slice()
        };
    }

    const allVals = [...(rawData.OPC || []), ...(rawData.SRC || []), ...(rawData.SBC || [])].filter(v => v !== null && !isNaN(v));
    if (!allVals.length) {
        return {
            OPC: (rawData.OPC || []).slice(),
            SRC: (rawData.SRC || []).slice(),
            SBC: (rawData.SBC || []).slice()
        };
    }

    const minVal = Math.min(...allVals);
    const maxVal = Math.max(...allVals);
    const range = (maxVal - minVal) || 1;
    const nudge = range * 0.016; // 1.6% visual offset

    const opcOut = [];
    const srcOut = [];
    const sbcOut = [];

    const len = dashboardData.trends.labels ? dashboardData.trends.labels.length : (rawData.OPC || []).length;
    for (let i = 0; i < len; i++) {
        const o = rawData.OPC && rawData.OPC[i] !== undefined ? rawData.OPC[i] : null;
        const s = rawData.SRC && rawData.SRC[i] !== undefined ? rawData.SRC[i] : null;
        const b = rawData.SBC && rawData.SBC[i] !== undefined ? rawData.SBC[i] : null;

        let oNudge = 0;
        let sNudge = 0;
        let bNudge = 0;

        // Micro-offset when OPC and SRC occupy the same visual level
        if (o !== null && s !== null && Math.abs(o - s) < (range * 0.04)) {
            oNudge -= nudge;
            sNudge += nudge;
        }

        if (b !== null && s !== null && Math.abs(b - s) < (range * 0.04)) {
            bNudge += nudge * 1.5;
        } else if (b !== null && o !== null && Math.abs(b - o) < (range * 0.04)) {
            bNudge += nudge * 1.5;
        }

        opcOut.push(o !== null ? +(o + oNudge).toFixed(3) : null);
        srcOut.push(s !== null ? +(s + sNudge).toFixed(3) : null);
        sbcOut.push(b !== null ? +(b + bNudge).toFixed(3) : null);
    }

    return { OPC: opcOut, SRC: srcOut, SBC: sbcOut };
}

// Initialize Trend Chart
function initChart(param) {
    const canvas = document.getElementById('trendChart');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (param) currentTrendParam = param;
    
    Chart.defaults.color = themeToken('--text-secondary');
    Chart.defaults.font.family = "system-ui";
    
    _eraLineActive = (currentTrendParam === 'Strength_28D') && !!dashboardData.strength28Era;

    const dispData = getTrendDisplayData(currentTrendParam);
    const isIsolated = currentTrendFilter !== 'all';

    const datasets = [
        {
            label: 'OPC (Ordinary Portland)',
            data: dispData.OPC,
            borderColor: CEMENT_COLORS.OPC.border,
            backgroundColor: isIsolated && currentTrendFilter === 'OPC' ? CEMENT_COLORS.OPC.bg : 'transparent',
            borderWidth: 2.5,
            tension: 0.35,
            fill: false,
            spanGaps: false,
            pointStyle: 'circle',
            pointRadius: 5,
            pointHoverRadius: 8,
            pointBackgroundColor: CEMENT_COLORS.OPC.border,
            pointBorderColor: themeToken('--panel-bg') || '#ffffff',
            pointBorderWidth: 2,
            order: 3,
            hidden: currentTrendFilter !== 'all' && currentTrendFilter !== 'OPC'
        },
        {
            label: 'SRC (Sulfate Resisting)',
            data: dispData.SRC,
            borderColor: CEMENT_COLORS.SRC.border,
            backgroundColor: isIsolated && currentTrendFilter === 'SRC' ? CEMENT_COLORS.SRC.bg : 'transparent',
            borderWidth: 2.5,
            tension: 0.35,
            borderDash: [8, 4],
            fill: false,
            spanGaps: false,
            pointStyle: 'rectRot',
            pointRadius: 7,
            pointHoverRadius: 10,
            pointBackgroundColor: CEMENT_COLORS.SRC.border,
            pointBorderColor: themeToken('--panel-bg') || '#ffffff',
            pointBorderWidth: 2,
            order: 2, // In front of OPC
            hidden: currentTrendFilter !== 'all' && currentTrendFilter !== 'SRC'
        },
        {
            label: 'SBC',
            data: dispData.SBC,
            borderColor: CEMENT_COLORS.SBC.border,
            backgroundColor: isIsolated && currentTrendFilter === 'SBC' ? CEMENT_COLORS.SBC.bg : 'transparent',
            borderWidth: 2.5,
            tension: 0.35,
            borderDash: [3, 3],
            fill: false,
            spanGaps: false,
            pointStyle: 'triangle',
            pointRadius: 7,
            pointHoverRadius: 10,
            pointBackgroundColor: CEMENT_COLORS.SBC.border,
            pointBorderColor: themeToken('--panel-bg') || '#ffffff',
            pointBorderWidth: 2,
            order: 1, // In front of OPC
            hidden: currentTrendFilter !== 'all' && currentTrendFilter !== 'SBC'
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
                    labels: {
                        padding: 15,
                        usePointStyle: true,
                        font: { size: 12, family: "system-ui" }
                    },
                    onClick: (e, legendItem, legend) => {
                        const index = legendItem.datasetIndex;
                        const ci = legend.chart;
                        if (ci.isDatasetVisible(index)) {
                            ci.hide(index);
                            legendItem.hidden = true;
                        } else {
                            ci.show(index);
                            legendItem.hidden = false;
                        }
                        syncTrendFilterButtons();
                    },
                    onHover: (e, legendItem, legend) => {
                        if (currentTrendFilter !== 'all') return;
                        const chart = legend.chart;
                        const idx = legendItem.datasetIndex;
                        chart.data.datasets.forEach((ds, i) => {
                            if (i === idx) {
                                ds.borderWidth = 3.8;
                                ds.order = 0;
                            } else {
                                ds.borderWidth = 1.5;
                                ds.order = i + 2;
                            }
                        });
                        chart.update('none');
                    },
                    onLeave: (e, legendItem, legend) => {
                        if (currentTrendFilter !== 'all') return;
                        const chart = legend.chart;
                        chart.data.datasets.forEach((ds, i) => {
                            ds.borderWidth = 2.5;
                            ds.order = i === 0 ? 3 : (i === 1 ? 2 : 1);
                        });
                        chart.update('none');
                    }
                },
                tooltip: {
                    backgroundColor: themeToken('--chart-tooltip'),
                    titleFont: { size: 13, family: "system-ui", weight: 'bold' },
                    bodyFont: { size: 12, family: "system-ui" },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: true,
                    usePointStyle: true,
                    callbacks: {
                        label: function(context) {
                            const cKey = context.datasetIndex === 0 ? 'OPC' : (context.datasetIndex === 1 ? 'SRC' : 'SBC');
                            const orig = dashboardData?.trends?.data?.[currentTrendParam]?.[cKey]?.[context.dataIndex];
                            const displayVal = orig !== null && orig !== undefined ? Number(orig).toFixed(2) : 'N/A';
                            const unit = getParamUnit(currentTrendParam).replace(/.*\((.*)\)/, '$1') || '';
                            const cLabel = context.dataset.label.split(' ')[0];
                            const isOffset = trendOffsetActive && orig !== null && orig !== undefined && Math.abs(context.raw - orig) > 0.001;
                            return ` ${cLabel}: ${displayVal} ${unit}${isOffset ? ' [offset for view]' : ''}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: themeToken('--chart-grid'), drawBorder: false }
                },
                y: {
                    grid: { color: themeToken('--chart-grid'), drawBorder: false },
                    title: { display: true, text: getParamUnit(currentTrendParam), font: { size: 12 } }
                }
            },
            interaction: { mode: 'index', intersect: false }
        }
    });

    applyTrendFilterStyles();
}

// Update Trend Chart dynamically
function updateChart(param) {
    if (!trendChart) return;
    if (param) currentTrendParam = param;
    _eraLineActive = (currentTrendParam === 'Strength_28D') && !!dashboardData.strength28Era;

    const dispData = getTrendDisplayData(currentTrendParam);
    trendChart.data.datasets[0].data = dispData.OPC;
    trendChart.data.datasets[1].data = dispData.SRC;
    trendChart.data.datasets[2].data = dispData.SBC;
    trendChart.options.scales.y.title.text = getParamUnit(currentTrendParam);

    applyTrendFilterStyles();
    trendChart.update();
}

function applyTrendFilterStyles() {
    if (!trendChart) return;
    const isIsolated = currentTrendFilter !== 'all';

    // OPC
    trendChart.data.datasets[0].hidden = isIsolated && currentTrendFilter !== 'OPC';
    trendChart.data.datasets[0].fill = isIsolated && currentTrendFilter === 'OPC';
    trendChart.data.datasets[0].backgroundColor = (isIsolated && currentTrendFilter === 'OPC') ? CEMENT_COLORS.OPC.bg : 'transparent';
    trendChart.data.datasets[0].borderWidth = (isIsolated && currentTrendFilter === 'OPC') ? 3 : 2.5;
    trendChart.data.datasets[0].order = (isIsolated && currentTrendFilter === 'OPC') ? 0 : 3;

    // SRC
    trendChart.data.datasets[1].hidden = isIsolated && currentTrendFilter !== 'SRC';
    trendChart.data.datasets[1].fill = isIsolated && currentTrendFilter === 'SRC';
    trendChart.data.datasets[1].backgroundColor = (isIsolated && currentTrendFilter === 'SRC') ? CEMENT_COLORS.SRC.bg : 'transparent';
    trendChart.data.datasets[1].borderDash = (isIsolated && currentTrendFilter === 'SRC') ? [] : [8, 4];
    trendChart.data.datasets[1].borderWidth = (isIsolated && currentTrendFilter === 'SRC') ? 3 : 2.5;
    trendChart.data.datasets[1].order = (isIsolated && currentTrendFilter === 'SRC') ? 0 : 2;

    // SBC
    trendChart.data.datasets[2].hidden = isIsolated && currentTrendFilter !== 'SBC';
    trendChart.data.datasets[2].fill = isIsolated && currentTrendFilter === 'SBC';
    trendChart.data.datasets[2].backgroundColor = (isIsolated && currentTrendFilter === 'SBC') ? CEMENT_COLORS.SBC.bg : 'transparent';
    trendChart.data.datasets[2].borderDash = (isIsolated && currentTrendFilter === 'SBC') ? [] : [3, 3];
    trendChart.data.datasets[2].borderWidth = (isIsolated && currentTrendFilter === 'SBC') ? 3 : 2.5;
    trendChart.data.datasets[2].order = (isIsolated && currentTrendFilter === 'SBC') ? 0 : 1;
}

function setupTrendChartControls() {
    const filters = document.querySelectorAll('.trend-cement-btn');
    filters.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetType = btn.getAttribute('data-type');
            if (currentTrendFilter === targetType && targetType !== 'all') {
                currentTrendFilter = 'all';
            } else {
                currentTrendFilter = targetType;
            }
            filters.forEach(b => {
                b.classList.toggle('active', b.getAttribute('data-type') === currentTrendFilter);
            });
            applyTrendFilterStyles();
            trendChart.update();
        });
    });

    const offsetToggle = document.getElementById('trendOffsetToggle');
    if (offsetToggle) {
        offsetToggle.addEventListener('change', (e) => {
            trendOffsetActive = e.target.checked;
            updateChart();
        });
    }
}

function syncTrendFilterButtons() {
    if (!trendChart) return;
    const opcVisible = trendChart.isDatasetVisible(0);
    const srcVisible = trendChart.isDatasetVisible(1);
    const sbcVisible = trendChart.isDatasetVisible(2);

    let activeType = 'all';
    if (opcVisible && !srcVisible && !sbcVisible) activeType = 'OPC';
    else if (!opcVisible && srcVisible && !sbcVisible) activeType = 'SRC';
    else if (!opcVisible && !srcVisible && sbcVisible) activeType = 'SBC';
    else if (opcVisible && srcVisible && sbcVisible) activeType = 'all';
    else activeType = 'custom';

    currentTrendFilter = activeType;
    document.querySelectorAll('.trend-cement-btn').forEach(btn => {
        btn.classList.toggle('active', btn.getAttribute('data-type') === activeType);
    });
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
    if (!table || !dashboardData || !dashboardData.correlation) return;
    const cols = dashboardData.correlation.columns || [];
    const matrix = dashboardData.correlation.matrix;
    const matrixDict = dashboardData.correlation.matrixDict;
    if (!cols.length || (!matrix && !matrixDict)) return;

    // Build header row
    let headerHTML = '<thead><tr><th>Feature</th>';
    cols.forEach(col => {
        headerHTML += `<th>${escapeHtml(col.replace(/_/g, ' '))}</th>`;
    });
    headerHTML += '</tr></thead>';

    // Build body rows
    let bodyHTML = '<tbody>';
    cols.forEach((rowCol, rIdx) => {
        bodyHTML += `<tr><td style="font-weight: 600; text-align: left; background: var(--panel-header); font-family: var(--font-sans);">${escapeHtml(rowCol.replace(/_/g, ' '))}</td>`;
        cols.forEach((colCol, cIdx) => {
            let val = 0;
            // 1. Try matrixDict if available
            if (matrixDict && matrixDict[rowCol] && matrixDict[rowCol][colCol] !== undefined) {
                val = matrixDict[rowCol][colCol];
            }
            // 2. Try 2D array by index: matrix[rIdx][cIdx]
            else if (Array.isArray(matrix)) {
                if (matrix[rIdx] && matrix[rIdx][cIdx] !== undefined) {
                    val = matrix[rIdx][cIdx];
                } else if (matrix[rowCol] && matrix[rowCol][colCol] !== undefined) {
                    val = matrix[rowCol][colCol];
                }
            }
            // 3. Try object dictionary: matrix[rowCol][colCol]
            else if (matrix && typeof matrix === 'object') {
                if (matrix[rowCol] && matrix[rowCol][colCol] !== undefined) {
                    val = matrix[rowCol][colCol];
                } else if (matrix[rIdx] && matrix[rIdx][cIdx] !== undefined) {
                    val = matrix[rIdx][cIdx];
                }
            }
            const numVal = typeof val === 'number' ? val : (parseFloat(val) || 0);
            const style = getCorrelationStyle(numVal);
            bodyHTML += `<td style="background-color: ${style.bg}; color: ${style.color}; font-weight: 600; text-align: center;">${numVal.toFixed(2)}</td>`;
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
        const recentAverage = dashboardData.ml[cTypeSelect.value]?.recentAverage;
        document.getElementById('opt_res_strength').innerText = recentAverage == null ? '--' : `${recentAverage.toFixed(1)} MPa`;
        document.getElementById('opt_res_model_strength').innerText = '--';
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

        const validationSource = modelData.modelBeatsRecentBaseline ? 'Validated model' : 'Recent average';
        r2El.innerText = `${validationSource} R²: ${modelData.r2 == null ? 'n/a' : `${(modelData.r2 * 100).toFixed(1)}%`}`;
        rmseEl.innerText = `${validationSource} RMSE: ${modelData.rmse == null ? 'n/a' : `${modelData.rmse} MPa`}`;

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
            const dr = modelData.modelDateRange || {};
            const range = dr.min && dr.max ? `${dr.min} → ${dr.max}` : 'n/a';
            trainEl.innerText = `XGBoost: ${modelData.modelTrainSamples || 0} completed 28-day tests · ${range}`;
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
            const recentAverage = dashboardData.ml[cType]?.recentAverage;
            document.getElementById('opt_res_strength').innerText = recentAverage == null ? '--' : `${recentAverage.toFixed(1)} MPa`;
            document.getElementById('opt_res_model_strength').innerText = '--';
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

            const modelInputsComplete = optInputs.every(id => document.getElementById(id).value !== '');
            let strengthHtml = modelMeta.recentAverage == null ? '--' : `${modelMeta.recentAverage.toFixed(1)} MPa`;
            let modelHtml = modelMeta.hasModel ? 'Enter all eight tests' : 'Unavailable';
            let advice = `<strong>Chemistry Engine:</strong><br>${chem.advice}`;

            if (modelMeta.hasModel && modelInputsComplete) {
                const res = await fetch('/api/predict', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(reqData)
                });
                if (!res.ok) throw new Error(`Strength prediction failed (${res.status})`);
                const result = await res.json();
                if (result.prediction !== undefined) {
                    strengthHtml = result.recentAverage == null ? '--' : `${result.recentAverage.toFixed(1)} MPa`;
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
                        modelHtml = 'Held for review';
                        advice += `<br><br><strong>TypeSafe review required before using this estimate.</strong>`;
                        document.getElementById('expectedDateBox').style.display = 'none';
                    } else {
                        modelHtml = result.mlPrediction == null ? 'Unavailable' : `${result.mlPrediction.toFixed(1)} MPa`;
                        advice += `<br><br><strong>${result.confidenceLabel}</strong>`;
                        if (result.predictionSource === 'recent_mean') {
                            advice += `<br>The model estimate is experimental. Compare it with the recent average; neither is a lab result.`;
                        } else {
                            advice += `<br>The model estimate is based on the entered tests.`;
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
                document.getElementById('expectedDateBox').style.display = 'none';
                if (!modelInputsComplete && modelMeta.hasModel) {
                    advice += '<br><br>Enter all eight tests to see the model estimate.';
                }
            }

            document.getElementById('opt_res_strength').innerText = strengthHtml;
            document.getElementById('opt_res_model_strength').innerText = modelHtml;
            document.getElementById('opt_advice').innerHTML = advice;
        } catch (e) {
            console.error(e);
            document.getElementById('opt_res_model_strength').innerText = 'Could not calculate';
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
        },
        economics: {
            currency: document.getElementById('raw_currency') ? document.getElementById('raw_currency').value : '$',
            fuel_price_per_ton: parseFloat(document.getElementById('raw_fuel_price') ? document.getElementById('raw_fuel_price').value : 350),
            plant_capacity_tpd: parseFloat(document.getElementById('raw_plant_capacity') ? document.getElementById('raw_plant_capacity').value : 5300),
            standard_calorific: 9800,
            standard_heat: 740,
            material_prices: {
                limestone: parseFloat(document.getElementById('raw_ls_price') ? document.getElementById('raw_ls_price').value : 8),
                shale: parseFloat(document.getElementById('raw_sh_price') ? document.getElementById('raw_sh_price').value : 12),
                sand: parseFloat(document.getElementById('raw_sd_price') ? document.getElementById('raw_sd_price').value : 18),
                pyrite: parseFloat(document.getElementById('raw_py_price') ? document.getElementById('raw_py_price').value : 45)
            }
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

    const econFields = {
        'fuel price': 'raw_fuel_price',
        'plant capacity': 'raw_plant_capacity',
        'limestone price': 'raw_ls_price',
        'clay price': 'raw_sh_price',
        'sand price': 'raw_sd_price',
        'corrector price': 'raw_py_price'
    };

    for (const [name, id] of Object.entries({
        'hfo heat': 'raw_hfo_heat',
        'hfo calorific': 'raw_hfo_cal',
        'hfo sulfur': 'raw_hfo_sulfur',
        ...extraFields,
        ...econFields,
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

        // Render Process Economics & Calorific Comparison
        if (data.economics) {
            renderProcessEconomics(data.economics);
        }

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

        if (rawMixMode === 'solve' && data.dry_proportions) {
            const p = data.dry_proportions;
            const lsEl = document.getElementById('raw_recipe_ls');
            const shEl = document.getElementById('raw_recipe_sh');
            const sdEl = document.getElementById('raw_recipe_sd');
            const pyEl = document.getElementById('raw_recipe_py');
            if (lsEl && p.Limestone != null) lsEl.value = Number(p.Limestone).toFixed(2);
            if (shEl && p.Clay != null) shEl.value = Number(p.Clay).toFixed(2);
            if (sdEl && p.Sand != null) sdEl.value = Number(p.Sand).toFixed(2);
            const pyVal = p['Slag'] ?? p['Iron Ore'] ?? p[Object.keys(p)[3]];
            if (pyEl && pyVal != null) pyEl.value = Number(pyVal).toFixed(2);
            updateRecipeTotals();
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
const rawMixPresets = {
    OPC: {
        material4Label: '4. Slag',
        recipe4Label: 'Slag %',
        isSlag: true,
        correctorChem: { SiO2: 23.60, Al2O3: 8.25, Fe2O3: 27.69, CaO: 32.15, MgO: 5.93, Na2O: 0.20, K2O: 0.50, SO3: 1.50, LOI: 0.90, H2O: 6.5 },
        targets: { LSF: 95.0, SM: 2.35, AM: 1.40 },
        recipe: { ls: 72.32, sh: 24.92, sd: 0.37, py: 2.39 }
    },
    SBC: {
        material4Label: '4. Slag',
        recipe4Label: 'Slag %',
        isSlag: true,
        correctorChem: { SiO2: 23.60, Al2O3: 8.25, Fe2O3: 27.69, CaO: 32.15, MgO: 5.93, Na2O: 0.20, K2O: 0.50, SO3: 1.50, LOI: 0.90, H2O: 6.5 },
        targets: { LSF: 94.0, SM: 2.35, AM: 1.40 },
        recipe: { ls: 72.06, sh: 25.16, sd: 0.37, py: 2.42 }
    },
    SRC: {
        material4Label: '4. Iron Ore',
        recipe4Label: 'Iron Ore %',
        isSlag: false,
        correctorChem: { SiO2: 49.00, Al2O3: 0.69, Fe2O3: 37.18, CaO: 1.00, MgO: 0.90, Na2O: 0.29, K2O: 0.81, SO3: 1.50, LOI: 8.55, H2O: 7.8 },
        targets: { LSF: 95.0, SM: 2.25, AM: 0.80 },
        recipe: { ls: 74.15, sh: 19.97, sd: 0.75, py: 5.13 }
    }
};

let rawCementType = 'OPC';
let rawMixMode = 'solve';

function applyRawMixPreset(cementType, autoCalculate = true) {
    rawCementType = cementType;
    const preset = rawMixPresets[cementType] || rawMixPresets.OPC;

    // Update UI Labels
    const mat4Label = document.getElementById('raw_material_4_label');
    const rec4Label = document.getElementById('raw_recipe_py_label');
    if (mat4Label) mat4Label.innerText = preset.material4Label;
    if (rec4Label) rec4Label.innerText = preset.recipe4Label;

    // Load corrector chemistry into inputs
    const c = preset.correctorChem;
    const setVal = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val;
    };

    setVal('raw_py_SiO2', c.SiO2.toFixed(2));
    setVal('raw_py_Al2O3', c.Al2O3.toFixed(2));
    setVal('raw_py_Fe2O3', c.Fe2O3.toFixed(2));
    setVal('raw_py_CaO', c.CaO.toFixed(2));
    setVal('raw_py_MgO', c.MgO.toFixed(2));
    setVal('raw_py_Na2O', c.Na2O.toFixed(2));
    setVal('raw_py_K2O', c.K2O.toFixed(2));
    setVal('raw_py_SO3', c.SO3.toFixed(2));
    setVal('raw_py_LOI', c.LOI.toFixed(2));
    setVal('raw_py_H2O', c.H2O.toFixed(1));

    // Load predefined clinker target moduli
    const t = preset.targets;
    setVal('raw_target_LSF', t.LSF.toFixed(1));
    setVal('raw_target_SM', t.SM.toFixed(2));
    setVal('raw_target_AM', t.AM.toFixed(2));

    // Load predefined recipe proportions
    const r = preset.recipe;
    setVal('raw_recipe_ls', r.ls.toFixed(2));
    setVal('raw_recipe_sh', r.sh.toFixed(2));
    setVal('raw_recipe_sd', r.sd.toFixed(2));
    setVal('raw_recipe_py', r.py.toFixed(2));

    updateRawMixTotals();
    updateRecipeTotals();

    if (autoCalculate) {
        calculateRawMixProportions();
    }
}

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
            applyRawMixPreset(e.target.value, true);
        });
    }

    if (btnSolve && btnCalc) {
        btnSolve.addEventListener('click', () => {
            rawMixMode = 'solve';
            btnSolve.classList.add('is-active');
            btnCalc.classList.remove('is-active');

            document.getElementById('rawmix_target_moduli_block').style.display = 'block';
            document.getElementById('rawmix_recipe_input_block').style.display = 'none';
            btnCalculate.innerText = 'Calculate Proportions';
            document.getElementById('rawmix_results_title').innerText = 'Clinker Quality & Mineral Phase Projections';

            calculateRawMixProportions();
        });

        btnCalc.addEventListener('click', () => {
            rawMixMode = 'recipe';
            btnCalc.classList.add('is-active');
            btnSolve.classList.remove('is-active');

            document.getElementById('rawmix_target_moduli_block').style.display = 'none';
            document.getElementById('rawmix_recipe_input_block').style.display = 'block';
            btnCalculate.innerText = 'Check Recipe';
            document.getElementById('rawmix_results_title').innerText = 'Recipe Projection Results';

            calculateRawMixProportions();
        });
    }

    // Add Excel Paste Support for the table
    const table = document.querySelector('.rawmix-input-table');
    if (table) {
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
                        const val = parseFloat(cells[j].trim().replace(',', '.'));
                        if (!isNaN(val)) {
                            input.value = val;
                        }
                    }
                }
            }
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

    // Auto-solve with predefined values immediately on startup
    const initialType = selectType ? selectType.value : 'OPC';
    applyRawMixPreset(initialType, true);
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


// ==========================================
// Period & Seasonal Averages Manager
// ==========================================
let _currentPeriodState = {
    periodType: 'all',
    season: '',
    quarter: '',
    months: '',
    year: 'all',
    activeKey: 'all'
};

function renderSummaryCards(data) {
    if (!data) return;

    // 1. Total Records
    const totalEl = document.getElementById('totalRecords');
    if (totalEl) totalEl.innerText = (data.totalRecords || 0).toLocaleString();

    const periodSub = document.getElementById('totalRecordsPeriod');
    if (periodSub) periodSub.textContent = data.periodLabel || 'All time';

    // 2. Average 28-Day Strength
    const s = data.avgStrength || {};
    const strengthEl = document.getElementById('avgStrength');
    if (strengthEl) {
        strengthEl.innerHTML = `
            <div style="font-size: 1.3rem; display: flex; flex-direction: column; gap: 0.25rem; margin-top: 0.4rem;">
                <div><span style="color: #38bdf8; font-size: 0.9rem; display: inline-block; width: 45px; text-align: left;">OPC:</span> ${s.OPC !== null && s.OPC !== undefined ? s.OPC : '--'} <span class="unit">MPa</span></div>
                <div><span style="color: #10b981; font-size: 0.9rem; display: inline-block; width: 45px; text-align: left;">SRC:</span> ${s.SRC !== null && s.SRC !== undefined ? s.SRC : '--'} <span class="unit">MPa</span></div>
                <div><span style="color: #8b5cf6; font-size: 0.9rem; display: inline-block; width: 45px; text-align: left;">SBC:</span> ${s.SBC !== null && s.SBC !== undefined ? s.SBC : '--'} <span class="unit">MPa</span></div>
                ${s.overall !== undefined && s.overall !== null ? `<div style="border-top: 1px dashed var(--panel-border); margin-top: 0.2rem; padding-top: 0.2rem; font-size: 0.8rem; color: var(--text-secondary);">Avg: <strong style="color: var(--text-primary); font-size: 0.95rem;">${s.overall}</strong> <span class="unit">MPa</span></div>` : ''}
            </div>`;
    }

    // 3. Average C3S
    const c = data.avgC3S || {};
    const c3sEl = document.getElementById('avgC3S');
    if (c3sEl) {
        c3sEl.innerHTML = `
            <div style="font-size: 1.3rem; display: flex; flex-direction: column; gap: 0.25rem; margin-top: 0.4rem;">
                <div><span style="color: #38bdf8; font-size: 0.9rem; display: inline-block; width: 45px; text-align: left;">OPC:</span> ${c.OPC !== null && c.OPC !== undefined ? c.OPC : '--'} <span class="unit">%</span></div>
                <div><span style="color: #10b981; font-size: 0.9rem; display: inline-block; width: 45px; text-align: left;">SRC:</span> ${c.SRC !== null && c.SRC !== undefined ? c.SRC : '--'} <span class="unit">%</span></div>
                <div><span style="color: #8b5cf6; font-size: 0.9rem; display: inline-block; width: 45px; text-align: left;">SBC:</span> ${c.SBC !== null && c.SBC !== undefined ? c.SBC : '--'} <span class="unit">%</span></div>
                ${c.overall !== undefined && c.overall !== null ? `<div style="border-top: 1px dashed var(--panel-border); margin-top: 0.2rem; padding-top: 0.2rem; font-size: 0.8rem; color: var(--text-secondary);">Avg: <strong style="color: var(--text-primary); font-size: 0.95rem;">${c.overall}</strong> <span class="unit">%</span></div>` : ''}
            </div>`;
    }

    // 4. Coverage Period
    const covEl = document.getElementById('yearsCoverage');
    if (covEl) covEl.innerText = data.yearsCoverage || '--';

    const covSub = document.getElementById('coveragePeriodSub');
    if (covSub) covSub.textContent = data.periodLabel || 'Laboratory historical record';

    // 5. Active Badges
    const badge = document.getElementById('activePeriodBadge');
    if (badge) badge.textContent = data.periodLabel || 'Full Dataset (All Time)';

    const yrBadge = document.getElementById('seasonsCardsYearBadge');
    if (yrBadge) {
        yrBadge.textContent = data.year && data.year !== 'all' ? `(Year ${data.year})` : '(All Years)';
    }

    const tblYrBadge = document.getElementById('seasonsTableYearBadge');
    if (tblYrBadge) {
        tblYrBadge.textContent = data.year && data.year !== 'all' ? `(Year ${data.year})` : '(All Years)';
    }

    // Sync button highlight states
    document.querySelectorAll('.quick-period-btn').forEach(btn => {
        const p = btn.getAttribute('data-period');
        if (p === _currentPeriodState.activeKey) {
            btn.classList.add('is-active');
        } else {
            btn.classList.remove('is-active');
        }
    });

    // 6. Render the 4 Seasonal Cards & Detailed Table
    renderSeasonalBenchmarkCards(data);
    renderSeasonalTable(data);
}

function renderSeasonalBenchmarkCards(data) {
    const container = document.getElementById('seasonalBenchmarkCards');
    if (!container) return;

    const breakdown = data.seasonalBreakdown || [];
    if (!breakdown.length) {
        container.innerHTML = '<div style="grid-column: 1 / -1; padding: 1rem; text-align: center; color: var(--text-secondary);">No seasonal data available</div>';
        return;
    }

    container.innerHTML = breakdown.map(item => {
        const isCurrent = _currentPeriodState.activeKey === ('season_' + item.key);
        const s = item.avgStrength || {};
        const c = item.avgC3S || {};
        const cardBorder = isCurrent ? 'var(--accent-strong)' : 'var(--panel-border)';
        const cardBg = isCurrent ? 'var(--accent-subtle)' : 'var(--panel-bg)';
        const cardShadow = isCurrent ? '0 0 12px rgba(72, 169, 148, 0.25)' : 'none';

        return `
            <div class="card seasonal-card-interactive" data-season="${escapeHtml(item.key)}" 
                 style="background: ${cardBg} !important; border: 1px solid ${cardBorder}; border-radius: var(--radius-panel); padding: 0.75rem 0.85rem; cursor: pointer; transition: all 180ms ease; box-shadow: ${cardShadow};"
                 title="Click to filter summary cards for ${escapeHtml(item.name)}">
                
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem; border-bottom: 1px solid var(--panel-border); padding-bottom: 0.35rem;">
                    <div style="font-weight: 700; font-size: 0.85rem; color: ${isCurrent ? 'var(--accent-strong)' : 'var(--text-primary)'}; display: flex; align-items: center; gap: 0.3rem;">
                        <span>${escapeHtml(item.icon)}</span>
                        <span>${escapeHtml(item.name)}</span>
                    </div>
                    <span style="font-size: 0.7rem; color: var(--text-secondary);">${escapeHtml(item.label)}</span>
                </div>

                <!-- 28-Day Strength Metric -->
                <div style="margin-bottom: 0.45rem;">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-size: 0.68rem; text-transform: uppercase; color: var(--text-secondary); font-weight: 600;">28D Strength</span>
                        <span style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); font-family: var(--font-mono);">${s.overall !== null && s.overall !== undefined ? s.overall : '--'} <span class="unit" style="font-size: 0.7rem;">MPa</span></span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.7rem; font-family: var(--font-mono); margin-top: 0.15rem; color: var(--text-muted);">
                        <span>OPC: <strong style="color: #38bdf8;">${s.OPC ?? '--'}</strong></span>
                        <span>SRC: <strong style="color: #10b981;">${s.SRC ?? '--'}</strong></span>
                        <span>SBC: <strong style="color: #8b5cf6;">${s.SBC ?? '--'}</strong></span>
                    </div>
                </div>

                <!-- C3S Metric -->
                <div style="margin-bottom: 0.45rem; border-top: 1px dashed var(--panel-border); padding-top: 0.35rem;">
                    <div style="display: flex; justify-content: space-between; align-items: baseline;">
                        <span style="font-size: 0.68rem; text-transform: uppercase; color: var(--text-secondary); font-weight: 600;">C₃S Content</span>
                        <span style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); font-family: var(--font-mono);">${c.overall !== null && c.overall !== undefined ? c.overall : '--'} <span class="unit" style="font-size: 0.7rem;">%</span></span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.7rem; font-family: var(--font-mono); margin-top: 0.15rem; color: var(--text-muted);">
                        <span>OPC: <strong style="color: #38bdf8;">${c.OPC ?? '--'}</strong></span>
                        <span>SRC: <strong style="color: #10b981;">${c.SRC ?? '--'}</strong></span>
                        <span>SBC: <strong style="color: #8b5cf6;">${c.SBC ?? '--'}</strong></span>
                    </div>
                </div>

                <!-- Records count footer -->
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.68rem; color: var(--text-secondary); border-top: 1px solid var(--panel-border); padding-top: 0.3rem;">
                    <span>${item.totalRecords.toLocaleString()} tests</span>
                    <span style="color: ${isCurrent ? 'var(--accent-strong)' : 'var(--text-muted)'}; font-weight: ${isCurrent ? '700' : 'normal'};">
                        ${isCurrent ? '● Active' : 'Select →'}
                    </span>
                </div>
            </div>
        `;
    }).join('');

    // Attach click handlers to the seasonal benchmark cards
    container.querySelectorAll('.seasonal-card-interactive').forEach(card => {
        card.addEventListener('click', () => {
            const seasonKey = card.getAttribute('data-season');
            setActivePeriod('season_' + seasonKey);
        });
    });
}

function renderSeasonalTable(data) {
    const tbody = document.getElementById('seasonalComparisonBody');
    if (!tbody) return;

    const breakdown = data.seasonalBreakdown || [];
    if (!breakdown.length) {
        tbody.innerHTML = '<tr><td colspan="11" style="text-align: center; padding: 1rem; color: var(--text-secondary);">No seasonal data available</td></tr>';
        return;
    }

    tbody.innerHTML = breakdown.map(item => {
        const isCurrent = _currentPeriodState.activeKey === ('season_' + item.key);
        const s = item.avgStrength || {};
        const c = item.avgC3S || {};
        const rowStyle = isCurrent 
            ? 'background: var(--panel-header); font-weight: 600; cursor: pointer;' 
            : 'cursor: pointer; transition: background 120ms ease;';
        return `
            <tr class="season-row" data-season="${escapeHtml(item.key)}" style="${rowStyle}" title="Click to filter dashboard by ${escapeHtml(item.name)}">
                <td style="padding: 0.45rem 0.6rem;">${escapeHtml(item.icon)} ${escapeHtml(item.name)}</td>
                <td style="padding: 0.45rem 0.6rem; color: var(--text-secondary);">${escapeHtml(item.label)}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono);">${item.totalRecords.toLocaleString()}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); border-left: 1px solid var(--panel-border); color: #38bdf8;">${s.OPC !== null && s.OPC !== undefined ? s.OPC : '--'}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); color: #10b981;">${s.SRC !== null && s.SRC !== undefined ? s.SRC : '--'}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); color: #8b5cf6;">${s.SBC !== null && s.SBC !== undefined ? s.SBC : '--'}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); font-weight: 650; color: var(--text-primary);">${s.overall !== null && s.overall !== undefined ? s.overall : '--'}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); border-left: 1px solid var(--panel-border); color: #38bdf8;">${c.OPC !== null && c.OPC !== undefined ? c.OPC : '--'}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); color: #10b981;">${c.SRC !== null && c.SRC !== undefined ? c.SRC : '--'}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); color: #8b5cf6;">${c.SBC !== null && c.SBC !== undefined ? c.SBC : '--'}</td>
                <td style="padding: 0.45rem 0.6rem; text-align: right; font-family: var(--font-mono); font-weight: 650; color: var(--text-primary);">${c.overall !== null && c.overall !== undefined ? c.overall : '--'}</td>
            </tr>
        `;
    }).join('');

    tbody.querySelectorAll('.season-row').forEach(row => {
        row.addEventListener('click', () => {
            const seasonKey = row.getAttribute('data-season');
            setActivePeriod('season_' + seasonKey);
        });
    });
}

let _averagesControlsInitialized = false;

function setupPeriodAveragesControls(initialAverages) {
    if (_averagesControlsInitialized) return;
    _averagesControlsInitialized = true;

    // Populate Year selector
    const yearSelect = document.getElementById('avgYearSelect');
    if (yearSelect && initialAverages && Array.isArray(initialAverages.availableYears)) {
        yearSelect.innerHTML = '<option value="all">All Years</option>' + 
            initialAverages.availableYears.map(y => `<option value="${y}">${y}</option>`).join('');
    }

    // Quick Season / Period Buttons
    document.querySelectorAll('.quick-period-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const periodKey = btn.getAttribute('data-period');
            const select3m = document.getElementById('avg3mSelect');
            if (select3m) select3m.value = '';
            setActivePeriod(periodKey);
        });
    });

    // 3 Months Dropdown
    const select3m = document.getElementById('avg3mSelect');
    if (select3m) {
        select3m.addEventListener('change', () => {
            const val = select3m.value;
            if (val) {
                setActivePeriod(val);
            } else {
                setActivePeriod('all');
            }
        });
    }

    // Year Dropdown
    if (yearSelect) {
        yearSelect.addEventListener('change', () => {
            _currentPeriodState.year = yearSelect.value;
            loadPeriodAverages();
        });
    }

    // Reset Button
    const resetBtn = document.getElementById('btnResetAvgPeriod');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            if (yearSelect) yearSelect.value = 'all';
            if (select3m) select3m.value = '';
            _currentPeriodState.year = 'all';
            setActivePeriod('all');
        });
    }

    // Toggle Detailed Table Drawer
    const toggleBtn = document.getElementById('btnToggleSeasonsTable');
    const drawer = document.getElementById('seasonalComparisonDrawer');
    if (toggleBtn && drawer) {
        toggleBtn.addEventListener('click', () => {
            const isHidden = drawer.style.display === 'none' || !drawer.style.display;
            drawer.style.display = isHidden ? 'block' : 'none';
            toggleBtn.textContent = isHidden ? '✕ Hide Detailed Table' : '📊 Detailed Table';
        });
    }
}

function setActivePeriod(periodKey) {
    _currentPeriodState.activeKey = periodKey;

    if (periodKey === 'all') {
        _currentPeriodState.periodType = 'all';
        _currentPeriodState.season = '';
        _currentPeriodState.quarter = '';
        _currentPeriodState.months = '';
    } else if (periodKey.startsWith('season_')) {
        _currentPeriodState.periodType = 'season';
        _currentPeriodState.season = periodKey.replace('season_', '');
        _currentPeriodState.quarter = '';
        _currentPeriodState.months = '';
    } else if (periodKey.startsWith('quarter_')) {
        _currentPeriodState.periodType = 'quarter';
        _currentPeriodState.quarter = periodKey.replace('quarter_', '');
        _currentPeriodState.season = '';
        _currentPeriodState.months = '';
    } else if (periodKey.startsWith('months_')) {
        _currentPeriodState.periodType = 'months';
        _currentPeriodState.months = periodKey.replace('months_', '');
        _currentPeriodState.season = '';
        _currentPeriodState.quarter = '';
    }

    loadPeriodAverages();
}

async function loadPeriodAverages() {
    const yearSelect = document.getElementById('avgYearSelect');
    const badge = document.getElementById('activePeriodBadge');

    const yearVal = yearSelect ? yearSelect.value : _currentPeriodState.year || 'all';

    const params = new URLSearchParams({
        period_type: _currentPeriodState.periodType,
        year: yearVal
    });

    if (_currentPeriodState.season) params.set('season', _currentPeriodState.season);
    if (_currentPeriodState.quarter) params.set('quarter', _currentPeriodState.quarter);
    if (_currentPeriodState.months) params.set('months', _currentPeriodState.months);

    if (badge) badge.textContent = 'Updating...';

    try {
        const resp = await fetch(`/api/averages?${params.toString()}`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();
        renderSummaryCards(data);
    } catch (err) {
        console.error('Failed to load period averages:', err);
        if (badge) badge.textContent = 'Error updating averages';
    }
}

function renderProcessEconomics(econ) {
    if (!econ) return;
    const cur = econ.currency || '$';
    const fuel = econ.fuel || {};
    const raw = econ.raw_materials || {};
    const baseline = econ.provider_baseline || {};

    // Update currency labels throughout DOM
    document.querySelectorAll('.currency-label').forEach(el => el.textContent = cur);
    for (let i = 1; i <= 7; i++) {
        const symEl = document.getElementById(`econ_currency_sym${i}`);
        if (symEl) symEl.textContent = cur;
    }

    // Top KPIs
    const elTot = document.getElementById('econ_total_clinker_cost');
    if (elTot) elTot.textContent = Number(econ.total_direct_cost_per_t_clinker || 0).toFixed(2);

    const elDayTot = document.getElementById('econ_daily_total_cost');
    if (elDayTot) elDayTot.textContent = Number(econ.daily_total_direct_cost || 0).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 });

    const elMatCl = document.getElementById('econ_mat_clinker_cost');
    if (elMatCl) elMatCl.textContent = Number(raw.cost_per_t_clinker || 0).toFixed(2);

    const elMeal = document.getElementById('econ_meal_cost');
    if (elMeal) elMeal.textContent = Number(raw.cost_per_t_rawmeal || 0).toFixed(2);

    const elFactor = document.getElementById('econ_meal_factor');
    if (elFactor) elFactor.textContent = Number(raw.meal_to_clinker_factor || 1.532).toFixed(3);

    const elFuelCost = document.getElementById('econ_fuel_cost');
    if (elFuelCost) elFuelCost.textContent = Number(fuel.cost_per_t_clinker || 0).toFixed(2);

    const elSfc = document.getElementById('econ_sfc_actual');
    if (elSfc) elSfc.textContent = Number(fuel.sfc_actual_kg_t || 0).toFixed(2);

    const elGcal = document.getElementById('econ_cost_gcal');
    if (elGcal) elGcal.textContent = Number(fuel.cost_per_gcal || 0).toFixed(2);

    const elGj = document.getElementById('econ_cost_gj');
    if (elGj) elGj.textContent = Number(fuel.cost_per_gj || 0).toFixed(2);

    // Badge & Calorific Comparison Alert Box
    const badge = document.getElementById('econ_status_badge');
    const alertBox = document.getElementById('econ_calorific_alert_box');

    const actualCal = Number(fuel.actual_calorific || 9800);
    const stdCal = Number(baseline.standard_calorific || 9800);
    const varKg = Number(fuel.sfc_var_kg_t || 0);
    const varPct = Number(fuel.sfc_var_pct || 0);
    const varCostCl = Number(fuel.cost_var_per_t_clinker || 0);
    const dailyVarCost = Number(fuel.daily_cost_var || 0);
    const dailyVarFuel = Number(fuel.daily_fuel_var_t || 0);
    const annualVarCost = Number(fuel.annual_cost_var || 0);

    if (fuel.status === 'penalty') {
        if (badge) {
            badge.style.background = 'rgba(239, 68, 68, 0.15)';
            badge.style.color = '#ef4444';
            badge.style.borderColor = '#ef4444';
            badge.textContent = `Calorific Deficit (-${fuel.calorific_deficit} kcal/kg)`;
        }
        if (alertBox) {
            alertBox.style.borderColor = 'rgba(239, 68, 68, 0.4)';
            alertBox.style.background = 'rgba(239, 68, 68, 0.06)';
            alertBox.innerHTML = `
                <div style="display:flex; align-items:flex-start; gap:0.6rem;">
                    <div style="font-size:1.4rem; line-height:1;">⚠️</div>
                    <div style="flex:1;">
                        <div style="font-weight:700; color:#ef4444; font-size:0.85rem; margin-bottom:0.25rem;">
                            Fuel Quality Penalty Alert: Delivered HFO (${actualCal.toLocaleString()} kcal/kg) is below Sinoma Design Standard (${stdCal.toLocaleString()} kcal/kg)
                        </div>
                        <div style="font-size:0.78rem; line-height:1.45; color:var(--text-primary);">
                            Because the calorific value is low, the kiln must burn 
                            <strong style="color:#ef4444; font-family:var(--font-mono);">${fuel.sfc_actual_kg_t.toFixed(2)} kg/t</strong> 
                            instead of the standard <strong style="font-family:var(--font-mono);">${fuel.sfc_std_kg_t.toFixed(2)} kg/t</strong> 
                            (an excess of <strong style="color:#ef4444; font-family:var(--font-mono);">+${varKg.toFixed(2)} kg fuel/ton clinker</strong> or 
                            <strong style="color:#ef4444; font-family:var(--font-mono);">+${varPct.toFixed(1)}%</strong>).
                        </div>
                        <div style="margin-top:0.4rem; display:flex; flex-wrap:wrap; gap:0.75rem; font-size:0.78rem; font-family:var(--font-mono);">
                            <span style="background:rgba(239,68,68,0.12); padding:2px 6px; border-radius:3px; color:#ef4444;">
                                Clinker Cost Penalty: <strong>+${cur}${varCostCl.toFixed(2)} / ton</strong>
                            </span>
                            <span style="background:rgba(239,68,68,0.12); padding:2px 6px; border-radius:3px; color:#ef4444;">
                                Extra Fuel Burned: <strong>+${dailyVarFuel.toFixed(1)} tons / day</strong>
                            </span>
                            <span style="background:rgba(239,68,68,0.12); padding:2px 6px; border-radius:3px; color:#ef4444;">
                                Daily Financial Loss: <strong>+${cur}${Math.abs(dailyVarCost).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0})} / day</strong>
                            </span>
                            <span style="background:rgba(239,68,68,0.12); padding:2px 6px; border-radius:3px; color:#ef4444;">
                                Annual Impact (310 d): <strong>+${cur}${Math.abs(annualVarCost).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0})} / yr</strong>
                            </span>
                        </div>
                    </div>
                </div>
            `;
        }
    } else if (fuel.status === 'optimal') {
        if (badge) {
            badge.style.background = 'rgba(16, 185, 129, 0.15)';
            badge.style.color = '#10b981';
            badge.style.borderColor = '#10b981';
            badge.textContent = `Superior Calorific (+${Math.abs(fuel.calorific_deficit)} kcal/kg)`;
        }
        if (alertBox) {
            alertBox.style.borderColor = 'rgba(16, 185, 129, 0.4)';
            alertBox.style.background = 'rgba(16, 185, 129, 0.06)';
            alertBox.innerHTML = `
                <div style="display:flex; align-items:flex-start; gap:0.6rem;">
                    <div style="font-size:1.4rem; line-height:1;">✨</div>
                    <div style="flex:1;">
                        <div style="font-weight:700; color:#10b981; font-size:0.85rem; margin-bottom:0.25rem;">
                            High Efficiency Fuel: Delivered HFO (${actualCal.toLocaleString()} kcal/kg) exceeds Sinoma Standard (${stdCal.toLocaleString()} kcal/kg)
                        </div>
                        <div style="font-size:0.78rem; line-height:1.45; color:var(--text-primary);">
                            Specific fuel consumption decreases to <strong style="color:#10b981; font-family:var(--font-mono);">${fuel.sfc_actual_kg_t.toFixed(2)} kg/t</strong> 
                            (saving <strong style="color:#10b981; font-family:var(--font-mono);">${Math.abs(varKg).toFixed(2)} kg fuel/ton</strong> or 
                            <strong style="color:#10b981; font-family:var(--font-mono);">${Math.abs(varPct).toFixed(1)}%</strong>), saving 
                            <strong style="color:#10b981; font-family:var(--font-mono);">${cur}${Math.abs(dailyVarCost).toLocaleString(undefined, {minimumFractionDigits:0, maximumFractionDigits:0})} / day</strong>.
                        </div>
                    </div>
                </div>
            `;
        }
    } else {
        if (badge) {
            badge.style.background = 'rgba(var(--accent-rgb, 72, 169, 148), 0.15)';
            badge.style.color = 'var(--accent)';
            badge.style.borderColor = 'var(--accent)';
            badge.textContent = 'Standard Baseline';
        }
        if (alertBox) {
            alertBox.style.borderColor = 'var(--panel-border)';
            alertBox.style.background = 'var(--panel-muted)';
            alertBox.innerHTML = `
                <div style="display:flex; align-items:center; gap:0.6rem; font-size:0.78rem;">
                    <span style="font-size:1.1rem;">✅</span>
                    <span>Delivered fuel calorific value matches <strong>Sinoma Sulaymaniyah Project Standard (${stdCal.toLocaleString()} kcal/kg)</strong>. Specific consumption is nominal at <strong>${fuel.sfc_actual_kg_t.toFixed(2)} kg HFO / ton clinker</strong> (${fuel.actual_heat} kcal/kg clinker).</span>
                </div>
            `;
        }
    }

    // Material Breakdown List
    const breakdownList = document.getElementById('econ_mat_breakdown_list');
    if (breakdownList && raw.breakdown_per_t_clinker) {
        breakdownList.replaceChildren();
        Object.entries(raw.breakdown_per_t_clinker).forEach(([mat, cost]) => {
            const unitPrice = raw.prices ? raw.prices[mat] : 0;
            const row = document.createElement('div');
            row.style.cssText = 'display:flex; justify-content:space-between; align-items:center; padding:0.25rem 0.4rem; background:var(--panel-muted); border-radius:2px;';
            row.innerHTML = `
                <span style="color:var(--text-secondary);">${mat} (@ ${cur}${Number(unitPrice).toFixed(2)}/t):</span>
                <strong style="font-family:var(--font-mono);">${cur}${Number(cost).toFixed(2)} / ton cl</strong>
            `;
            breakdownList.appendChild(row);
        });
    }
}
