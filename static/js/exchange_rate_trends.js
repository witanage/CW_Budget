// ============================================================
// Exchange Rate Trends - Chart.js Visualisations
// Single API call, single DB connection
// ============================================================

let ertCharts = { mainTrend: null, forecast: null, sourceComparison: null, volatility: null, spread: null };
let ertCache = null; // cached API response

let ertSettings = {
    period: 'daily',
    months: 6,
    forecastDays: 30,
    forecastHistory: 3,
    comparisonMonths: 3,
    showBuySell: true
};

const COLORS = {
    mid:       { line: '#0d6efd', fill: 'rgba(13, 110, 253, 0.10)' },
    buy:       { line: '#198754', fill: 'rgba(25, 135, 84, 0.08)' },
    sell:      { line: '#dc3545', fill: 'rgba(220, 53, 69, 0.08)' },
    forecast:  { line: '#6f42c1', fill: 'rgba(111, 66, 193, 0.10)' },
    band:      'rgba(111, 66, 193, 0.08)',
    cbsl: '#0d6efd', hnb: '#198754', pb: '#fd7e14', csv: '#6c757d', manual: '#20c997',
    spread:    { line: '#fd7e14', fill: 'rgba(253, 126, 20, 0.15)' },
    volatility: '#17a2b8'
};
const SOURCE_COLORS = { CBSL: COLORS.cbsl, HNB: COLORS.hnb, PB: COLORS.pb, CSV: COLORS.csv, Manual: COLORS.manual };

// ============================================================
// Init
// ============================================================
document.addEventListener('DOMContentLoaded', function () {
    setupControls();
    fetchAndRenderAll();
});

function setupControls() {
    document.querySelectorAll('#periodSelector .btn').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#periodSelector .btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            ertSettings.period = this.dataset.period;
            fetchAndRenderAll();
        });
    });

    document.getElementById('monthsSelector').addEventListener('change', function () {
        ertSettings.months = parseInt(this.value);
        fetchAndRenderAll();
    });

    document.getElementById('showBuySellToggle').addEventListener('change', function () {
        ertSettings.showBuySell = this.checked;
        if (ertCache) renderMainTrend(ertCache.trend);
    });

    document.getElementById('forecastDaysSelector').addEventListener('change', function () {
        ertSettings.forecastDays = parseInt(this.value);
        fetchAndRenderAll();
    });
    document.getElementById('forecastHistorySelector').addEventListener('change', function () {
        ertSettings.forecastHistory = parseInt(this.value);
        fetchAndRenderAll();
    });

    document.getElementById('comparisonMonthsSelector').addEventListener('change', function () {
        ertSettings.comparisonMonths = parseInt(this.value);
        fetchAndRenderAll();
    });

    document.getElementById('refreshAllChartsBtn').addEventListener('click', fetchAndRenderAll);
}

// ============================================================
// Single fetch  -> render all charts from one response
// ============================================================
async function fetchAndRenderAll() {
    try {
        const params = new URLSearchParams({
            period: ertSettings.period,
            months: ertSettings.months,
            forecast_days: ertSettings.forecastDays,
            forecast_history: ertSettings.forecastHistory,
            comparison_months: ertSettings.comparisonMonths
        });
        const res = await fetch(`/api/exchange-rate/trends/all?${params}`);
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || 'API error');

        ertCache = json;

        renderMainTrend(json.trend || []);
        renderForecast(json.forecast);
        renderSourceComparison(json.source_comparison || {});
        renderVolatility(json.monthly_volatility || []);
        renderSpread(json.trend || []);
    } catch (err) {
        console.error('Trends fetch error:', err);
        ['mainTrendChart', 'forecastChart', 'sourceComparisonChart', 'volatilityChart', 'spreadChart']
            .forEach(id => renderEmptyChart(id, err.message));
    }
}

// ============================================================
// Theme helper
// ============================================================
function chartDefaults() {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    return {
        gridColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
        textColor: isDark ? '#ccc' : '#555'
    };
}

// ============================================================
// 1. Main Trend
// ============================================================
function renderMainTrend(data) {
    if (!data || data.length === 0) { renderEmptyChart('mainTrendChart', 'No exchange rate data available'); return; }

    updateSummaryCards(data);

    const labels = data.map(d => {
        if (ertSettings.period === 'monthly') return `${d.year}-${String(d.month).padStart(2, '0')}`;
        if (ertSettings.period === 'weekly') return d.week_start;
        return d.date;
    });

    const midKey  = data[0].mid_rate !== undefined ? 'mid_rate' : 'avg_mid_rate';
    const buyKey  = 'avg_buy_rate';
    const sellKey = 'avg_sell_rate';

    const datasets = [{
        label: 'Mid Rate', data: data.map(d => d[midKey]),
        borderColor: COLORS.mid.line, backgroundColor: COLORS.mid.fill,
        borderWidth: 2, fill: true, tension: 0.3,
        pointRadius: data.length > 90 ? 0 : 2, pointHoverRadius: 5, order: 1
    }];

    if (ertSettings.showBuySell) {
        datasets.push({
            label: 'Buy Rate', data: data.map(d => d[buyKey]),
            borderColor: COLORS.buy.line, backgroundColor: COLORS.buy.fill,
            borderWidth: 1.5, borderDash: [4, 3], fill: false, tension: 0.3,
            pointRadius: 0, pointHoverRadius: 4, order: 2
        }, {
            label: 'Sell Rate', data: data.map(d => d[sellKey]),
            borderColor: COLORS.sell.line, backgroundColor: COLORS.sell.fill,
            borderWidth: 1.5, borderDash: [4, 3], fill: false, tension: 0.3,
            pointRadius: 0, pointHoverRadius: 4, order: 3
        });
    }
    renderLineChart('mainTrendChart', 'mainTrend', labels, datasets, 'LKR per USD');
}

// ============================================================
// 2. Forecast
// ============================================================
function renderForecast(fc) {
    if (!fc) { renderEmptyChart('forecastChart', 'Not enough data for forecast'); document.getElementById('forecastModelInfo').style.display = 'none'; return; }

    const history  = fc.history || [];
    const forecast = fc.points  || [];
    const model    = fc.model   || {};

    if (history.length === 0) { renderEmptyChart('forecastChart', 'Not enough data for forecast'); return; }

    const historyTail = history.slice(-Math.min(60, history.length));
    const allLabels = [...historyTail.map(d => d.date), ...forecast.map(d => d.date)];
    const histLen = historyTail.length;
    const lastMid = historyTail[historyTail.length - 1].mid_rate;

    const historicalData = [...historyTail.map(d => d.mid_rate), ...forecast.map(() => null)];
    const forecastData   = [...historyTail.slice(0, -1).map(() => null), lastMid, ...forecast.map(d => d.predicted_mid_rate)];
    const upperBand      = [...historyTail.slice(0, -1).map(() => null), lastMid, ...forecast.map(d => d.upper_bound)];
    const lowerBand      = [...historyTail.slice(0, -1).map(() => null), lastMid, ...forecast.map(d => d.lower_bound)];

    const datasets = [
        { label: 'Historical', data: historicalData, borderColor: COLORS.mid.line, backgroundColor: COLORS.mid.fill, borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0, pointHoverRadius: 4, order: 2 },
        { label: 'Forecast', data: forecastData, borderColor: COLORS.forecast.line, backgroundColor: COLORS.forecast.fill, borderWidth: 2.5, borderDash: [6, 4], fill: true, tension: 0.3, pointRadius: 0, pointHoverRadius: 4, order: 1 },
        { label: 'Upper 95%', data: upperBand, borderColor: 'rgba(111,66,193,0.3)', backgroundColor: COLORS.band, borderWidth: 1, borderDash: [2, 2], fill: '+1', tension: 0.3, pointRadius: 0, order: 3 },
        { label: 'Lower 95%', data: lowerBand, borderColor: 'rgba(111,66,193,0.3)', backgroundColor: COLORS.band, borderWidth: 1, borderDash: [2, 2], fill: false, tension: 0.3, pointRadius: 0, order: 4 }
    ];

    renderLineChart('forecastChart', 'forecast', allLabels, datasets, 'LKR per USD');
    addForecastDivider('forecastChart', 'forecast', histLen - 1);

    document.getElementById('forecastModelInfo').style.display = '';
    document.getElementById('modelSlope').textContent      = model.slope_per_day != null ? model.slope_per_day.toFixed(4) : '--';
    document.getElementById('modelRSquared').textContent    = model.r_squared    != null ? model.r_squared.toFixed(4)    : '--';
    document.getElementById('modelDataPoints').textContent  = model.data_points  || '--';
}

// ============================================================
// 3. Source Comparison
// ============================================================
function renderSourceComparison(sources) {
    const sourceNames = Object.keys(sources);
    if (sourceNames.length === 0) { renderEmptyChart('sourceComparisonChart', 'No multi-source data available'); return; }

    const dateSet = new Set();
    sourceNames.forEach(s => sources[s].forEach(d => dateSet.add(d.date)));
    const labels = Array.from(dateSet).sort();

    const datasets = sourceNames.map(src => {
        const dateMap = {};
        sources[src].forEach(d => { dateMap[d.date] = d.mid_rate; });
        return {
            label: src, data: labels.map(date => dateMap[date] ?? null),
            borderColor: SOURCE_COLORS[src] || '#6c757d', borderWidth: 2,
            fill: false, tension: 0.3, pointRadius: labels.length > 60 ? 0 : 2,
            pointHoverRadius: 4, spanGaps: true
        };
    });
    renderLineChart('sourceComparisonChart', 'sourceComparison', labels, datasets, 'Mid Rate (LKR)');
}

// ============================================================
// 4. Volatility
// ============================================================
function renderVolatility(data) {
    if (!data || data.length === 0) { renderEmptyChart('volatilityChart', 'No monthly data'); return; }

    const labels    = data.map(d => `${d.year}-${String(d.month).padStart(2, '0')}`);
    const volData   = data.map(d => d.buy_rate_volatility || 0);
    const rangeData = data.map(d => d.month_range || 0);
    const { gridColor, textColor } = chartDefaults();

    if (ertCharts.volatility) ertCharts.volatility.destroy();
    const ctx = document.getElementById('volatilityChart').getContext('2d');
    ertCharts.volatility = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Volatility (Std Dev)', data: volData, backgroundColor: 'rgba(23,162,184,0.6)', borderColor: COLORS.volatility, borderWidth: 1, borderRadius: 3, yAxisID: 'y' },
                { label: 'Month Range', data: rangeData, type: 'line', borderColor: COLORS.sell.line, backgroundColor: 'transparent', borderWidth: 2, tension: 0.3, pointRadius: 3, yAxisID: 'y1' }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { labels: { color: textColor, font: { size: 11 } } }, tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(4) || '--'}` } } },
            scales: {
                x: { ticks: { color: textColor, font: { size: 10 } }, grid: { color: gridColor } },
                y:  { position: 'left',  title: { display: true, text: 'Std Dev', color: textColor, font: { size: 10 } }, ticks: { color: textColor, font: { size: 10 } }, grid: { color: gridColor } },
                y1: { position: 'right', title: { display: true, text: 'Range (LKR)', color: textColor, font: { size: 10 } }, ticks: { color: textColor, font: { size: 10 } }, grid: { drawOnChartArea: false } }
            }
        }
    });
}

// ============================================================
// 5. Spread (reuses trend data - no extra fetch)
// ============================================================
function renderSpread(data) {
    if (!data || data.length === 0) { renderEmptyChart('spreadChart', 'No spread data'); return; }

    const labels = data.map(d => d.date || `${d.year}-${String(d.month).padStart(2, '0')}`);
    const spreadData = data.map(d => {
        const buy  = d.avg_buy_rate || 0;
        const sell = d.avg_sell_rate || 0;
        return parseFloat((sell - buy).toFixed(4));
    });

    renderLineChart('spreadChart', 'spread', labels, [{
        label: 'Buy-Sell Spread', data: spreadData,
        borderColor: COLORS.spread.line, backgroundColor: COLORS.spread.fill,
        borderWidth: 1.5, fill: true, tension: 0.3, pointRadius: 0, pointHoverRadius: 4
    }], 'Spread (LKR)');
}

// ============================================================
// Summary Cards
// ============================================================
function updateSummaryCards(data) {
    if (!data || data.length === 0) return;
    const latest  = data[data.length - 1];
    const midKey  = latest.mid_rate !== undefined ? 'mid_rate' : 'avg_mid_rate';
    const buyKey  = 'avg_buy_rate';
    const sellKey = 'avg_sell_rate';

    const todayMid = latest[midKey];
    document.getElementById('todayMidRate').textContent = todayMid != null ? todayMid.toFixed(2) : '--';
    document.getElementById('todayRateDate').textContent = latest.date || latest.month_start || '';

    const thirtyIdx = Math.max(0, data.length - 31);
    const thirtyAgo = data[thirtyIdx];
    if (thirtyAgo && todayMid != null) {
        const oldMid = thirtyAgo[midKey];
        if (oldMid != null) {
            const diff = todayMid - oldMid;
            const pct  = ((diff / oldMid) * 100).toFixed(2);
            const el   = document.getElementById('thirtyDayChange');
            const pctEl = document.getElementById('thirtyDayPct');
            const iconEl = document.getElementById('changeIcon');
            el.textContent  = (diff >= 0 ? '+' : '') + diff.toFixed(2);
            pctEl.textContent = (diff >= 0 ? '+' : '') + pct + '%';
            if (diff > 0)      { el.className = 'mb-0 ert-change-up';      iconEl.className = 'ert-stat-icon bg-danger';  iconEl.innerHTML = '<i class="fas fa-arrow-up"></i>'; }
            else if (diff < 0) { el.className = 'mb-0 ert-change-down';    iconEl.className = 'ert-stat-icon bg-success'; iconEl.innerHTML = '<i class="fas fa-arrow-down"></i>'; }
            else               { el.className = 'mb-0 ert-change-neutral'; iconEl.className = 'ert-stat-icon bg-secondary'; iconEl.innerHTML = '<i class="fas fa-minus"></i>'; }
        }
    }

    const spreads = data.map(d => (d[sellKey] || 0) - (d[buyKey] || 0)).filter(v => v > 0);
    if (spreads.length > 0) document.getElementById('avgSpread').textContent = (spreads.reduce((a, b) => a + b, 0) / spreads.length).toFixed(2);

    if (latest.buy_rate_volatility != null) document.getElementById('volatilityValue').textContent = latest.buy_rate_volatility.toFixed(4);
}

// ============================================================
// Shared chart helpers
// ============================================================
function renderLineChart(canvasId, chartKey, labels, datasets, yLabel) {
    const { gridColor, textColor } = chartDefaults();
    if (ertCharts[chartKey]) ertCharts[chartKey].destroy();

    const ctx = document.getElementById(canvasId).getContext('2d');
    ertCharts[chartKey] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true, maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: { labels: { color: textColor, font: { size: 11 }, usePointStyle: true, pointStyle: 'line' } },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.85)', titleColor: '#fff', bodyColor: '#ddd',
                    borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 10,
                    callbacks: { label: ctx => { const v = ctx.parsed.y; return v != null ? `${ctx.dataset.label}: ${v.toFixed(4)}` : ''; } }
                }
            },
            scales: {
                x: { ticks: { color: textColor, font: { size: 10 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 20 }, grid: { color: gridColor } },
                y: { title: { display: true, text: yLabel, color: textColor, font: { size: 11 } }, ticks: { color: textColor, font: { size: 10 } }, grid: { color: gridColor } }
            }
        }
    });
}

function renderEmptyChart(canvasId, message) {
    const chartKey = Object.keys(ertCharts).find(k => { const c = document.getElementById(canvasId); return c && ertCharts[k] && ertCharts[k].canvas === c; });
    if (chartKey && ertCharts[chartKey]) ertCharts[chartKey].destroy();
    const { textColor } = chartDefaults();
    const ctx = document.getElementById(canvasId).getContext('2d');
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.font = '14px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillStyle = textColor; ctx.textAlign = 'center';
    ctx.fillText(message || 'No data available', ctx.canvas.width / 2, ctx.canvas.height / 2);
}

function addForecastDivider(canvasId, chartKey, xIndex) {
    const chart = ertCharts[chartKey];
    if (!chart) return;
    const originalDraw = chart.draw.bind(chart);
    chart.draw = function () {
        originalDraw();
        const meta = chart.getDatasetMeta(0);
        if (!meta.data[xIndex]) return;
        const x = meta.data[xIndex].x, yAxis = chart.scales.y, ctx = chart.ctx;
        ctx.save();
        ctx.beginPath(); ctx.setLineDash([5, 5]); ctx.strokeStyle = 'rgba(150,150,150,0.6)'; ctx.lineWidth = 1.5;
        ctx.moveTo(x, yAxis.top); ctx.lineTo(x, yAxis.bottom); ctx.stroke();
        ctx.setLineDash([]); ctx.font = '10px sans-serif'; ctx.fillStyle = 'rgba(150,150,150,0.8)'; ctx.textAlign = 'center';
        ctx.fillText('Forecast', x + 35, yAxis.top + 12); ctx.restore();
    };
    chart.draw();
}
