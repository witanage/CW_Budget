// ============================================================
// Exchange Rate Trends - Chart.js Visualisations
// ============================================================

// Chart instances
let ertCharts = {
    mainTrend: null,
    forecast: null,
    sourceComparison: null,
    volatility: null,
    spread: null
};

// Current settings
let ertSettings = {
    period: 'daily',
    months: 6,
    forecastDays: 30,
    forecastHistory: 3,
    comparisonMonths: 3,
    showBuySell: true
};

// Colour palette
const COLORS = {
    mid:       { line: '#0d6efd', fill: 'rgba(13, 110, 253, 0.10)' },
    buy:       { line: '#198754', fill: 'rgba(25, 135, 84, 0.08)' },
    sell:      { line: '#dc3545', fill: 'rgba(220, 53, 69, 0.08)' },
    forecast:  { line: '#6f42c1', fill: 'rgba(111, 66, 193, 0.10)' },
    band:      'rgba(111, 66, 193, 0.08)',
    cbsl:      '#0d6efd',
    hnb:       '#198754',
    pb:        '#fd7e14',
    csv:       '#6c757d',
    manual:    '#20c997',
    spread:    { line: '#fd7e14', fill: 'rgba(253, 126, 20, 0.15)' },
    volatility: '#17a2b8'
};

const SOURCE_COLORS = { CBSL: COLORS.cbsl, HNB: COLORS.hnb, PB: COLORS.pb, CSV: COLORS.csv, Manual: COLORS.manual };

// ============================================================
// Initialisation
// ============================================================
document.addEventListener('DOMContentLoaded', function () {
    setupControls();
    loadAllCharts();
});

function setupControls() {
    // Period selector
    document.querySelectorAll('#periodSelector .btn').forEach(btn => {
        btn.addEventListener('click', function () {
            document.querySelectorAll('#periodSelector .btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            ertSettings.period = this.dataset.period;
            loadMainTrend();
        });
    });

    // Month history selector
    document.getElementById('monthsSelector').addEventListener('change', function () {
        ertSettings.months = parseInt(this.value);
        loadMainTrend();
        loadSpreadChart();
    });

    // Buy/Sell toggle
    document.getElementById('showBuySellToggle').addEventListener('change', function () {
        ertSettings.showBuySell = this.checked;
        loadMainTrend();
    });

    // Forecast selectors
    document.getElementById('forecastDaysSelector').addEventListener('change', function () {
        ertSettings.forecastDays = parseInt(this.value);
        loadForecast();
    });
    document.getElementById('forecastHistorySelector').addEventListener('change', function () {
        ertSettings.forecastHistory = parseInt(this.value);
        loadForecast();
    });

    // Source comparison months
    document.getElementById('comparisonMonthsSelector').addEventListener('change', function () {
        ertSettings.comparisonMonths = parseInt(this.value);
        loadSourceComparison();
    });

    // Refresh button
    document.getElementById('refreshAllChartsBtn').addEventListener('click', loadAllCharts);
}

function loadAllCharts() {
    loadMainTrend();
    loadForecast();
    loadSourceComparison();
    loadVolatility();
    loadSpreadChart();
}

// ============================================================
// Chart defaults helper
// ============================================================
function chartDefaults() {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    return {
        gridColor: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
        textColor: isDark ? '#ccc' : '#555'
    };
}

// ============================================================
// 1. Main Trend Chart (Past + Present)
// ============================================================
async function loadMainTrend() {
    try {
        const res = await fetch(`/api/exchange-rate/trends?period=${ertSettings.period}&months=${ertSettings.months}`);
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || 'Failed to load trends');

        const data = json.data;
        if (!data || data.length === 0) {
            renderEmptyChart('mainTrendChart', 'No exchange rate data available');
            return;
        }

        updateSummaryCards(data);

        const labels = data.map(d => {
            if (ertSettings.period === 'monthly') return `${d.year}-${String(d.month).padStart(2, '0')}`;
            if (ertSettings.period === 'weekly') return d.week_start;
            return d.date;
        });

        const midKey = ertSettings.period === 'daily'
            ? (data[0].mid_rate !== undefined ? 'mid_rate' : 'avg_mid_rate')
            : 'avg_mid_rate';
        const buyKey = ertSettings.period === 'daily'
            ? (data[0].avg_buy_rate !== undefined ? 'avg_buy_rate' : 'buy_rate')
            : 'avg_buy_rate';
        const sellKey = ertSettings.period === 'daily'
            ? (data[0].avg_sell_rate !== undefined ? 'avg_sell_rate' : 'sell_rate')
            : 'avg_sell_rate';

        const datasets = [{
            label: 'Mid Rate',
            data: data.map(d => d[midKey]),
            borderColor: COLORS.mid.line,
            backgroundColor: COLORS.mid.fill,
            borderWidth: 2,
            fill: true,
            tension: 0.3,
            pointRadius: data.length > 90 ? 0 : 2,
            pointHoverRadius: 5,
            order: 1
        }];

        if (ertSettings.showBuySell) {
            datasets.push({
                label: 'Buy Rate',
                data: data.map(d => d[buyKey]),
                borderColor: COLORS.buy.line,
                backgroundColor: COLORS.buy.fill,
                borderWidth: 1.5,
                borderDash: [4, 3],
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                order: 2
            }, {
                label: 'Sell Rate',
                data: data.map(d => d[sellKey]),
                borderColor: COLORS.sell.line,
                backgroundColor: COLORS.sell.fill,
                borderWidth: 1.5,
                borderDash: [4, 3],
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                order: 3
            });
        }

        renderLineChart('mainTrendChart', 'mainTrend', labels, datasets, 'LKR per USD');
    } catch (err) {
        console.error('Main trend chart error:', err);
        renderEmptyChart('mainTrendChart', err.message);
    }
}

// ============================================================
// 2. Forecast Chart
// ============================================================
async function loadForecast() {
    try {
        const res = await fetch(`/api/exchange-rate/trends/forecast?days=${ertSettings.forecastDays}&history_months=${ertSettings.forecastHistory}`);
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || 'Failed to load forecast');

        const history = json.history || [];
        const forecast = json.forecast || [];
        const model = json.model || {};

        if (history.length === 0) {
            renderEmptyChart('forecastChart', 'Not enough data for forecast');
            return;
        }

        // Show last portion of history + full forecast
        const historyTail = history.slice(-Math.min(60, history.length));

        const allLabels = [
            ...historyTail.map(d => d.date),
            ...forecast.map(d => d.date)
        ];

        const histLen = historyTail.length;

        // Historical mid rate (padded with nulls for forecast zone)
        const historicalData = [
            ...historyTail.map(d => d.mid_rate),
            ...forecast.map(() => null)
        ];

        // Forecast line (starts from last historical point for continuity)
        const forecastData = [
            ...historyTail.slice(0, -1).map(() => null),
            historyTail[historyTail.length - 1].mid_rate,
            ...forecast.map(d => d.predicted_mid_rate)
        ];

        // Confidence bands
        const upperBand = [
            ...historyTail.slice(0, -1).map(() => null),
            historyTail[historyTail.length - 1].mid_rate,
            ...forecast.map(d => d.upper_bound)
        ];
        const lowerBand = [
            ...historyTail.slice(0, -1).map(() => null),
            historyTail[historyTail.length - 1].mid_rate,
            ...forecast.map(d => d.lower_bound)
        ];

        const datasets = [
            {
                label: 'Historical',
                data: historicalData,
                borderColor: COLORS.mid.line,
                backgroundColor: COLORS.mid.fill,
                borderWidth: 2,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                order: 2
            },
            {
                label: 'Forecast',
                data: forecastData,
                borderColor: COLORS.forecast.line,
                backgroundColor: COLORS.forecast.fill,
                borderWidth: 2.5,
                borderDash: [6, 4],
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                order: 1
            },
            {
                label: 'Upper 95%',
                data: upperBand,
                borderColor: 'rgba(111, 66, 193, 0.3)',
                backgroundColor: COLORS.band,
                borderWidth: 1,
                borderDash: [2, 2],
                fill: '+1',
                tension: 0.3,
                pointRadius: 0,
                order: 3
            },
            {
                label: 'Lower 95%',
                data: lowerBand,
                borderColor: 'rgba(111, 66, 193, 0.3)',
                backgroundColor: COLORS.band,
                borderWidth: 1,
                borderDash: [2, 2],
                fill: false,
                tension: 0.3,
                pointRadius: 0,
                order: 4
            }
        ];

        renderLineChart('forecastChart', 'forecast', allLabels, datasets, 'LKR per USD');

        // Draw vertical divider line after rendering
        addForecastDivider('forecastChart', 'forecast', histLen - 1);

        // Update model info
        document.getElementById('forecastModelInfo').style.display = '';
        document.getElementById('modelSlope').textContent = model.slope_per_day != null ? model.slope_per_day.toFixed(4) : '--';
        document.getElementById('modelRSquared').textContent = model.r_squared != null ? model.r_squared.toFixed(4) : '--';
        document.getElementById('modelDataPoints').textContent = model.data_points || '--';

    } catch (err) {
        console.error('Forecast chart error:', err);
        renderEmptyChart('forecastChart', err.message);
        document.getElementById('forecastModelInfo').style.display = 'none';
    }
}

// ============================================================
// 3. Source Comparison Chart
// ============================================================
async function loadSourceComparison() {
    try {
        const res = await fetch(`/api/exchange-rate/trends/source-comparison?months=${ertSettings.comparisonMonths}`);
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || 'Failed to load comparison');

        const sources = json.sources || {};
        const sourceNames = Object.keys(sources);

        if (sourceNames.length === 0) {
            renderEmptyChart('sourceComparisonChart', 'No multi-source data available');
            return;
        }

        // Build union of all dates
        const dateSet = new Set();
        sourceNames.forEach(s => sources[s].forEach(d => dateSet.add(d.date)));
        const labels = Array.from(dateSet).sort();

        const datasets = sourceNames.map(src => {
            const dateMap = {};
            sources[src].forEach(d => { dateMap[d.date] = d.mid_rate; });
            return {
                label: src,
                data: labels.map(date => dateMap[date] ?? null),
                borderColor: SOURCE_COLORS[src] || '#6c757d',
                borderWidth: 2,
                fill: false,
                tension: 0.3,
                pointRadius: labels.length > 60 ? 0 : 2,
                pointHoverRadius: 4,
                spanGaps: true
            };
        });

        renderLineChart('sourceComparisonChart', 'sourceComparison', labels, datasets, 'Mid Rate (LKR)');
    } catch (err) {
        console.error('Source comparison error:', err);
        renderEmptyChart('sourceComparisonChart', err.message);
    }
}

// ============================================================
// 4. Volatility Chart (monthly bar)
// ============================================================
async function loadVolatility() {
    try {
        const res = await fetch('/api/exchange-rate/trends?period=monthly&months=12');
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || 'Failed to load volatility');

        const data = json.data || [];
        if (data.length === 0) {
            renderEmptyChart('volatilityChart', 'No monthly data');
            return;
        }

        const labels = data.map(d => `${d.year}-${String(d.month).padStart(2, '0')}`);
        const volData = data.map(d => d.buy_rate_volatility || 0);
        const rangeData = data.map(d => d.month_range || 0);

        const { gridColor, textColor } = chartDefaults();

        if (ertCharts.volatility) ertCharts.volatility.destroy();

        const ctx = document.getElementById('volatilityChart').getContext('2d');
        ertCharts.volatility = new Chart(ctx, {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Volatility (Std Dev)',
                        data: volData,
                        backgroundColor: 'rgba(23, 162, 184, 0.6)',
                        borderColor: COLORS.volatility,
                        borderWidth: 1,
                        borderRadius: 3,
                        yAxisID: 'y'
                    },
                    {
                        label: 'Month Range',
                        data: rangeData,
                        type: 'line',
                        borderColor: COLORS.sell.line,
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        tension: 0.3,
                        pointRadius: 3,
                        yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: textColor, font: { size: 11 } } },
                    tooltip: { callbacks: { label: ctx => `${ctx.dataset.label}: ${ctx.parsed.y?.toFixed(4) || '--'}` } }
                },
                scales: {
                    x: { ticks: { color: textColor, font: { size: 10 } }, grid: { color: gridColor } },
                    y: {
                        position: 'left',
                        title: { display: true, text: 'Std Dev', color: textColor, font: { size: 10 } },
                        ticks: { color: textColor, font: { size: 10 } },
                        grid: { color: gridColor }
                    },
                    y1: {
                        position: 'right',
                        title: { display: true, text: 'Range (LKR)', color: textColor, font: { size: 10 } },
                        ticks: { color: textColor, font: { size: 10 } },
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    } catch (err) {
        console.error('Volatility chart error:', err);
        renderEmptyChart('volatilityChart', err.message);
    }
}

// ============================================================
// 5. Spread Chart
// ============================================================
async function loadSpreadChart() {
    try {
        const res = await fetch(`/api/exchange-rate/trends?period=daily&months=${ertSettings.months}`);
        const json = await res.json();
        if (!res.ok) throw new Error(json.error || 'Failed to load spread data');

        const data = json.data || [];
        if (data.length === 0) {
            renderEmptyChart('spreadChart', 'No spread data');
            return;
        }

        const labels = data.map(d => d.date);
        const spreadData = data.map(d => {
            const buy = d.avg_buy_rate || d.buy_rate || 0;
            const sell = d.avg_sell_rate || d.sell_rate || 0;
            return parseFloat((sell - buy).toFixed(4));
        });

        const datasets = [{
            label: 'Buy-Sell Spread',
            data: spreadData,
            borderColor: COLORS.spread.line,
            backgroundColor: COLORS.spread.fill,
            borderWidth: 1.5,
            fill: true,
            tension: 0.3,
            pointRadius: 0,
            pointHoverRadius: 4
        }];

        renderLineChart('spreadChart', 'spread', labels, datasets, 'Spread (LKR)');
    } catch (err) {
        console.error('Spread chart error:', err);
        renderEmptyChart('spreadChart', err.message);
    }
}

// ============================================================
// Summary Cards
// ============================================================
function updateSummaryCards(data) {
    if (!data || data.length === 0) return;

    const latest = data[data.length - 1];
    const midKey = latest.mid_rate !== undefined ? 'mid_rate' : 'avg_mid_rate';
    const buyKey = latest.avg_buy_rate !== undefined ? 'avg_buy_rate' : 'buy_rate';
    const sellKey = latest.avg_sell_rate !== undefined ? 'avg_sell_rate' : 'sell_rate';

    // Today's rate
    const todayMid = latest[midKey];
    document.getElementById('todayMidRate').textContent = todayMid != null ? todayMid.toFixed(2) : '--';
    const dateLabel = latest.date || latest.month_start || '';
    document.getElementById('todayRateDate').textContent = dateLabel;

    // 30-day change
    const thirtyIdx = Math.max(0, data.length - 31);
    const thirtyAgo = data[thirtyIdx];
    if (thirtyAgo && todayMid != null) {
        const oldMid = thirtyAgo[midKey];
        if (oldMid != null) {
            const diff = todayMid - oldMid;
            const pct = ((diff / oldMid) * 100).toFixed(2);
            const el = document.getElementById('thirtyDayChange');
            const pctEl = document.getElementById('thirtyDayPct');
            const iconEl = document.getElementById('changeIcon');

            el.textContent = (diff >= 0 ? '+' : '') + diff.toFixed(2);
            pctEl.textContent = (diff >= 0 ? '+' : '') + pct + '%';

            if (diff > 0) {
                el.className = 'mb-0 ert-change-up';
                iconEl.className = 'ert-stat-icon bg-danger';
                iconEl.innerHTML = '<i class="fas fa-arrow-up"></i>';
            } else if (diff < 0) {
                el.className = 'mb-0 ert-change-down';
                iconEl.className = 'ert-stat-icon bg-success';
                iconEl.innerHTML = '<i class="fas fa-arrow-down"></i>';
            } else {
                el.className = 'mb-0 ert-change-neutral';
                iconEl.className = 'ert-stat-icon bg-secondary';
                iconEl.innerHTML = '<i class="fas fa-minus"></i>';
            }
        }
    }

    // Average spread
    const spreads = data.map(d => {
        const b = d[buyKey] || d.avg_buy_rate || 0;
        const s = d[sellKey] || d.avg_sell_rate || 0;
        return s - b;
    }).filter(v => v > 0);
    if (spreads.length > 0) {
        const avgSpread = spreads.reduce((a, b) => a + b, 0) / spreads.length;
        document.getElementById('avgSpread').textContent = avgSpread.toFixed(2);
    }

    // Volatility (if monthly data available, use last month)
    if (latest.buy_rate_volatility != null) {
        document.getElementById('volatilityValue').textContent = latest.buy_rate_volatility.toFixed(4);
    }
}

// ============================================================
// Chart Rendering Helpers
// ============================================================
function renderLineChart(canvasId, chartKey, labels, datasets, yLabel) {
    const { gridColor, textColor } = chartDefaults();

    if (ertCharts[chartKey]) ertCharts[chartKey].destroy();

    const ctx = document.getElementById(canvasId).getContext('2d');
    ertCharts[chartKey] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: {
                legend: {
                    labels: { color: textColor, font: { size: 11 }, usePointStyle: true, pointStyle: 'line' }
                },
                tooltip: {
                    backgroundColor: 'rgba(0,0,0,0.85)',
                    titleColor: '#fff',
                    bodyColor: '#ddd',
                    borderColor: 'rgba(255,255,255,0.1)',
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        label: function (ctx) {
                            const val = ctx.parsed.y;
                            return val != null ? `${ctx.dataset.label}: ${val.toFixed(4)}` : '';
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: textColor,
                        font: { size: 10 },
                        maxRotation: 45,
                        autoSkip: true,
                        maxTicksLimit: 20
                    },
                    grid: { color: gridColor }
                },
                y: {
                    title: { display: true, text: yLabel, color: textColor, font: { size: 11 } },
                    ticks: { color: textColor, font: { size: 10 } },
                    grid: { color: gridColor }
                }
            }
        }
    });
}

function renderEmptyChart(canvasId, message) {
    const chartKey = Object.keys(ertCharts).find(k => {
        const c = document.getElementById(canvasId);
        return c && ertCharts[k] && ertCharts[k].canvas === c;
    });
    if (chartKey && ertCharts[chartKey]) ertCharts[chartKey].destroy();

    const { textColor } = chartDefaults();
    const ctx = document.getElementById(canvasId).getContext('2d');

    // Draw message on canvas
    ctx.clearRect(0, 0, ctx.canvas.width, ctx.canvas.height);
    ctx.font = '14px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillStyle = textColor;
    ctx.textAlign = 'center';
    ctx.fillText(message || 'No data available', ctx.canvas.width / 2, ctx.canvas.height / 2);
}

// Plugin to draw a vertical dashed divider between history and forecast
function addForecastDivider(canvasId, chartKey, xIndex) {
    const chart = ertCharts[chartKey];
    if (!chart) return;

    const originalDraw = chart.draw.bind(chart);
    chart.draw = function () {
        originalDraw();
        const meta = chart.getDatasetMeta(0);
        if (!meta.data[xIndex]) return;
        const x = meta.data[xIndex].x;
        const yAxis = chart.scales.y;
        const ctx = chart.ctx;

        ctx.save();
        ctx.beginPath();
        ctx.setLineDash([5, 5]);
        ctx.strokeStyle = 'rgba(150, 150, 150, 0.6)';
        ctx.lineWidth = 1.5;
        ctx.moveTo(x, yAxis.top);
        ctx.lineTo(x, yAxis.bottom);
        ctx.stroke();

        // Label
        ctx.setLineDash([]);
        ctx.font = '10px sans-serif';
        ctx.fillStyle = 'rgba(150, 150, 150, 0.8)';
        ctx.textAlign = 'center';
        ctx.fillText('Forecast', x + 35, yAxis.top + 12);
        ctx.restore();
    };
    chart.draw();
}
