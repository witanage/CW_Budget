// ============================================================
// Exchange Rate Trends — SPA page integration
// Buy Rate only — called by dashboard.js → loadPageData('rateTrends')
// ============================================================

(function () {
    'use strict';

    // --------------- State ---------------
    var _charts = {};
    var _cache  = null;
    var _bound  = false;

    var _s = {
        period: 'daily',
        months: 1,
        forecastDays: 7,
        forecastHistory: 3,
        compMonths: 1,
        intradayDate: null,
        intradayLimit: 50,
        intradayTimezone: 'Asia/Colombo'
    };

    // --------------- Colours ---------------
    var C = {
        buy:  { line: '#0d6efd', fill: 'rgba(13,110,253,0.10)' },
        fc:   { line: '#6f42c1', fill: 'rgba(111,66,193,0.10)' },
        band: 'rgba(111,66,193,0.08)',
        vol:  '#17a2b8',
        range: '#dc3545'
    };
    var SRC_CLR = { CBSL: '#0d6efd', HNB: '#198754', PB: '#fd7e14', SAMPATH: '#dc3545', CSV: '#6c757d', Manual: '#20c997' };

    // ===================================================================
    // Public entry — called each time the user navigates to Rate Trends
    // ===================================================================
    window.loadRateTrends = function () {
        if (!_bound) {
            _initIntradayDate();
            _bindControls();
            _syncDropdownValues();
            _bound = true;
        }
        _fetchAll();
        _fetchIntraday();
    };

    // ===================================================================
    // Initialize intraday date to today
    // ===================================================================
    function _initIntradayDate() {
        var today = new Date();
        var yyyy = today.getFullYear();
        var mm = String(today.getMonth() + 1).padStart(2, '0');
        var dd = String(today.getDate()).padStart(2, '0');
        var todayStr = yyyy + '-' + mm + '-' + dd;
        _s.intradayDate = todayStr;

        var dateEl = document.getElementById('ertIntradayDate');
        if (dateEl) {
            dateEl.value = todayStr;
            dateEl.max = todayStr;
        }
    }

    // ===================================================================
    // Sync dropdown values with state
    // ===================================================================
    function _syncDropdownValues() {
        var monthsEl = document.getElementById('ertMonthsSelector');
        if (monthsEl) {
            monthsEl.value = _s.months;
        }

        var forecastDaysEl = document.getElementById('ertForecastDays');
        if (forecastDaysEl) {
            forecastDaysEl.value = _s.forecastDays;
        }

        var forecastHistoryEl = document.getElementById('ertForecastHistory');
        if (forecastHistoryEl) {
            forecastHistoryEl.value = _s.forecastHistory;
        }

        var compMonthsEl = document.getElementById('ertCompMonths');
        if (compMonthsEl) {
            compMonthsEl.value = _s.compMonths;
        }

        var intradayLimitEl = document.getElementById('ertIntradayLimit');
        if (intradayLimitEl) {
            intradayLimitEl.value = _s.intradayLimit;
        }
    }

    // ===================================================================
    // Bind controls (once)
    // ===================================================================
    function _bindControls() {
        // Period selector removed - always uses 'daily' (default in _s.period)

        _on('ertMonthsSelector',     'change', function () { _s.months           = +this.value; _fetchAll(); });
        _on('ertForecastDays',       'change', function () { _s.forecastDays     = +this.value; _fetchAll(); });
        _on('ertForecastHistory',    'change', function () { _s.forecastHistory  = +this.value; _fetchAll(); });
        _on('ertCompMonths',         'change', function () { _s.compMonths       = +this.value; _fetchAll(); });
        _on('ertRefreshBtn',         'click',  function () { _cache = null; _fetchAll(); _fetchIntraday(); });
        _on('ertIntradayDate',       'change', function () { _s.intradayDate     = this.value; _fetchIntraday(); });
        _on('ertIntradayLimit',      'change', function () { _s.intradayLimit    = +this.value; _fetchIntraday(); });
        _on('ertIntradayTimezone',   'change', function () { _s.intradayTimezone = this.value; _fetchIntraday(); });
        _on('ertAiInsightsBtn',      'click',  function () { _showAiInsights(); });
        _on('aiUserBankSelect',      'change', function () { _showAiInsights(); });
        _on('salaryCalcBtn',         'click',  function () { _showSalaryCalculator(); });
    }

    function _on(id, evt, fn) {
        var el = document.getElementById(id);
        if (el) el.addEventListener(evt, fn);
    }

    // ===================================================================
    // Single API fetch
    // ===================================================================
    function _fetchAll() {
        // Hide global loading spinner if it's active (for standalone page)
        if (typeof hideLoading === 'function') {
            hideLoading();
        }

        _show('ertLoading', true);
        _show('ertError',   false);
        _show('ertContent',  false);

        var params = new URLSearchParams({
            period:            _s.period,
            months:            _s.months,
            forecast_days:     _s.forecastDays,
            forecast_history:  _s.forecastHistory,
            comparison_months: _s.compMonths
        });

        fetch('/api/exchange-rate/trends/all?' + params)
            .then(function (res) {
                if (!res.ok) {
                    return res.json().catch(function () { return {}; }).then(function (j) {
                        throw new Error(j.error || 'Server error ' + res.status);
                    });
                }
                return res.json();
            })
            .then(function (data) {
                _cache = data;
                _show('ertLoading', false);
                _show('ertContent', true);

                _renderTrend(data.trend || []);
                _renderForecast(data.forecast);
                _renderSources(data.source_comparison || {});
                _renderVolatility(data.monthly_volatility || []);
            })
            .catch(function (err) {
                console.error('ERT fetch error:', err);
                _show('ertLoading', false);
                _show('ertError', true);
                var msg = document.getElementById('ertErrorMsg');
                if (msg) msg.textContent = err.message || 'Failed to load exchange rate data.';
            });
    }

    // ===================================================================
    // Helpers
    // ===================================================================
    function _show(id, vis) {
        var el = document.getElementById(id);
        if (el) el.style.display = vis ? '' : 'none';
    }

    function _txt(id, val) {
        var el = document.getElementById(id);
        if (el) el.textContent = val;
    }

    function _theme() {
        var dark = document.documentElement.getAttribute('data-theme') !== 'light';
        return {
            grid: dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
            text: dark ? '#ccc' : '#555'
        };
    }

    function _destroy(key) {
        if (_charts[key]) { _charts[key].destroy(); _charts[key] = null; }
    }

    // ===================================================================
    // 1. Main Trend Chart (buy rate only)
    // ===================================================================
    function _renderTrend(data) {
        if (!data.length) { _emptyCanvas('ertTrendChart', 'No exchange rate data available'); return; }

        _updateCards(data);

        var labels = data.map(function (d) {
            if (_s.period === 'monthly') return d.year + '-' + String(d.month).padStart(2, '0');
            if (_s.period === 'weekly')  return d.week_start;
            return d.date;
        });

        var ds = [{
            label: 'Buy Rate (USD/LKR)',
            data: data.map(function (d) { return d.buy_rate; }),
            borderColor: C.buy.line, backgroundColor: C.buy.fill,
            borderWidth: 2, fill: true, tension: 0.3,
            pointRadius: data.length > 90 ? 0 : 2, pointHoverRadius: 5
        }];

        _lineChart('ertTrendChart', 'trend', labels, ds, 'Buy Rate (LKR)');
    }

    // ===================================================================
    // 2. Forecast Chart (buy rate)
    // ===================================================================
    function _renderForecast(fc) {
        var info = document.getElementById('ertModelInfo');

        if (!fc || !fc.history || fc.history.length < 7) {
            _emptyCanvas('ertForecastChart', 'Not enough data for forecast');
            if (info) info.style.display = 'none';
            return;
        }

        var hist  = fc.history.slice(-60);
        var pts   = fc.points || [];
        var model = fc.model  || {};

        var allLabels = hist.map(function (d) { return d.date; })
                            .concat(pts.map(function (d) { return d.date; }));

        var lastRate = hist[hist.length - 1].buy_rate;

        var hData = hist.map(function (d) { return d.buy_rate; })
                        .concat(pts.map(function () { return null; }));

        var pad = hist.slice(0, -1).map(function () { return null; });

        var fData = pad.concat([lastRate]).concat(pts.map(function (d) { return d.predicted_buy_rate; }));
        var upper = pad.concat([lastRate]).concat(pts.map(function (d) { return d.upper_bound; }));
        var lower = pad.concat([lastRate]).concat(pts.map(function (d) { return d.lower_bound; }));

        var ds = [
            { label: 'Historical Buy Rate', data: hData, borderColor: C.buy.line, backgroundColor: C.buy.fill,
              borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0, order: 2 },
            { label: 'Forecast', data: fData, borderColor: C.fc.line, backgroundColor: C.fc.fill,
              borderWidth: 2.5, borderDash: [6, 4], fill: true, tension: 0.3, pointRadius: 0, order: 1 },
            { label: 'Upper 95%', data: upper, borderColor: 'rgba(111,66,193,0.3)', backgroundColor: C.band,
              borderWidth: 1, borderDash: [2, 2], fill: '+1', tension: 0.3, pointRadius: 0, order: 3 },
            { label: 'Lower 95%', data: lower, borderColor: 'rgba(111,66,193,0.3)', backgroundColor: C.band,
              borderWidth: 1, borderDash: [2, 2], fill: false, tension: 0.3, pointRadius: 0, order: 4 }
        ];

        _lineChart('ertForecastChart', 'forecast', allLabels, ds, 'Buy Rate (LKR)');

        // Draw vertical divider at history/forecast boundary
        var divIdx = hist.length - 1;
        var chart  = _charts.forecast;
        if (chart) {
            var origDraw = chart.draw.bind(chart);
            chart.draw = function () {
                origDraw();
                var meta = chart.getDatasetMeta(0);
                if (!meta.data[divIdx]) return;
                var x   = meta.data[divIdx].x;
                var yA  = chart.scales.y;
                var ctx = chart.ctx;
                ctx.save();
                ctx.beginPath();
                ctx.setLineDash([5, 5]);
                ctx.strokeStyle = 'rgba(150,150,150,0.6)';
                ctx.lineWidth   = 1.5;
                ctx.moveTo(x, yA.top);
                ctx.lineTo(x, yA.bottom);
                ctx.stroke();
                ctx.setLineDash([]);
                ctx.font      = '10px sans-serif';
                ctx.fillStyle = 'rgba(150,150,150,0.8)';
                ctx.textAlign = 'center';
                ctx.fillText('Forecast \u2192', x + 40, yA.top + 12);
                ctx.restore();
            };
            chart.draw();
        }

        // Model info
        if (info) {
            info.style.display = '';
            _txt('ertSlope',   model.slope_per_day != null ? model.slope_per_day.toFixed(4) : '--');
            _txt('ertR2',      model.r_squared     != null ? model.r_squared.toFixed(4)     : '--');
            _txt('ertDataPts', model.data_points    || '--');
        }
    }

    // ===================================================================
    // 3. Source Comparison (buy rate per bank)
    // ===================================================================
    function _renderSources(sources) {
        var names = Object.keys(sources);
        if (!names.length) { _emptyCanvas('ertSourceChart', 'No multi-source data available'); return; }

        var dateSet = {};
        names.forEach(function (s) {
            sources[s].forEach(function (d) { dateSet[d.date] = true; });
        });
        var labels = Object.keys(dateSet).sort();

        var ds = names.map(function (src) {
            var map = {};
            sources[src].forEach(function (d) { map[d.date] = d.buy_rate; });
            return {
                label: src,
                data: labels.map(function (dt) { return map[dt] != null ? map[dt] : null; }),
                borderColor: SRC_CLR[src] || '#6c757d', borderWidth: 2,
                fill: false, tension: 0.3,
                pointRadius: labels.length > 60 ? 0 : 2,
                pointHoverRadius: 4, spanGaps: true
            };
        });

        _lineChart('ertSourceChart', 'source', labels, ds, 'Buy Rate (LKR)');
    }

    // ===================================================================
    // 4. Volatility (bar + line combo, buy rate)
    // ===================================================================
    function _renderVolatility(data) {
        if (!data.length) { _emptyCanvas('ertVolChart', 'No monthly data available'); return; }

        var labels = data.map(function (d) { return d.year + '-' + String(d.month).padStart(2, '0'); });
        var vol    = data.map(function (d) { return d.buy_rate_volatility || 0; });
        var rng    = data.map(function (d) { return d.month_range || 0; });
        var t      = _theme();

        _destroy('vol');
        var ctx = document.getElementById('ertVolChart');
        if (!ctx) return;

        _charts.vol = new Chart(ctx.getContext('2d'), {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Volatility (Std Dev)', data: vol,
                        backgroundColor: 'rgba(23,162,184,0.6)',
                        borderColor: C.vol, borderWidth: 1, borderRadius: 3, yAxisID: 'y'
                    },
                    {
                        label: 'Buy Rate Range', data: rng, type: 'line',
                        borderColor: C.range, backgroundColor: 'transparent',
                        borderWidth: 2, tension: 0.3, pointRadius: 3, yAxisID: 'y1'
                    }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { labels: { color: t.text, font: { size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                return ctx.dataset.label + ': ' + (ctx.parsed.y != null ? ctx.parsed.y.toFixed(4) : '--');
                            }
                        }
                    }
                },
                scales: {
                    x:  { ticks: { color: t.text, font: { size: 10 } }, grid: { color: t.grid } },
                    y:  { position: 'left',  title: { display: true, text: 'Std Dev',    color: t.text, font: { size: 10 } }, ticks: { color: t.text, font: { size: 10 } }, grid: { color: t.grid } },
                    y1: { position: 'right', title: { display: true, text: 'Range (LKR)', color: t.text, font: { size: 10 } }, ticks: { color: t.text, font: { size: 10 } }, grid: { drawOnChartArea: false } }
                }
            }
        });
    }

    // ===================================================================
    // Summary Cards (buy rate)
    // ===================================================================
    function _updateCards(data) {
        if (!data.length) return;

        var last = data[data.length - 1];
        var rate = last.buy_rate;

        _txt('ertTodayRate', rate != null ? rate.toFixed(2) : '--');
        _txt('ertTodayDate', last.date || last.month_start || '');

        // 30-day change
        var agoIdx = Math.max(0, data.length - 31);
        var ago    = data[agoIdx];
        if (ago && rate != null) {
            var old = ago.buy_rate;
            if (old != null) {
                var diff = rate - old;
                var pct  = ((diff / old) * 100).toFixed(2);

                var el   = document.getElementById('ert30DayChange');
                var pEl  = document.getElementById('ert30DayPct');
                var icon = document.getElementById('ertChangeIcon');

                if (el) {
                    el.textContent = (diff >= 0 ? '+' : '') + diff.toFixed(2);
                    el.className   = 'mb-0 ert-change-' + (diff > 0 ? 'up' : diff < 0 ? 'down' : 'neutral');
                }
                if (pEl) {
                    pEl.textContent = (diff >= 0 ? '+' : '') + pct + '%';
                }
                if (icon) {
                    icon.className = 'ert-stat-icon ' + (diff > 0 ? 'bg-danger' : diff < 0 ? 'bg-success' : 'bg-secondary');
                    icon.innerHTML = '<i class="fas fa-arrow-' + (diff > 0 ? 'up' : diff < 0 ? 'down' : 'right') + '"></i>';
                }
            }
        }

        // Min/Max
        var minRate = null, maxRate = null;
        data.forEach(function (d) {
            var r = d.buy_rate;
            if (r != null) {
                if (minRate === null || r < minRate) minRate = r;
                if (maxRate === null || r > maxRate) maxRate = r;
            }
        });
        if (minRate != null && maxRate != null) {
            _txt('ertMinMax', minRate.toFixed(2) + ' - ' + maxRate.toFixed(2));
        }
    }

    // ===================================================================
    // Shared line chart renderer
    // ===================================================================
    function _lineChart(canvasId, key, labels, datasets, yLabel) {
        var t = _theme();
        _destroy(key);
        var el = document.getElementById(canvasId);
        if (!el) return;

        _charts[key] = new Chart(el.getContext('2d'), {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: {
                        labels: { color: t.text, font: { size: 11 }, usePointStyle: true, pointStyle: 'line' },
                        onHover: function (evt, legendItem, legend) {
                            // Dim the line for the hovered legend item
                            var chart = legend.chart;
                            var datasetIndex = legendItem.datasetIndex;

                            // Store original alpha values if not already stored
                            chart.data.datasets.forEach(function (dataset, i) {
                                if (!dataset._originalBorderAlpha) {
                                    dataset._originalBorderAlpha = 1.0;
                                }
                                if (!dataset._originalBackgroundAlpha) {
                                    // Extract alpha from rgba string if it exists
                                    var bgColor = dataset.backgroundColor;
                                    if (typeof bgColor === 'string' && bgColor.startsWith('rgba')) {
                                        var match = bgColor.match(/rgba\([^,]+,[^,]+,[^,]+,([^)]+)\)/);
                                        dataset._originalBackgroundAlpha = match ? parseFloat(match[1]) : 0.1;
                                    } else {
                                        dataset._originalBackgroundAlpha = 0.1;
                                    }
                                }

                                // Dim the hovered dataset
                                if (i === datasetIndex) {
                                    // Reduce opacity by 70% (to 30%)
                                    var bc = dataset.borderColor;
                                    var rgb = _extractRGB(bc);
                                    dataset.borderColor = 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.3)';

                                    if (dataset.backgroundColor && dataset.backgroundColor !== 'transparent') {
                                        var bgRgb = _extractRGB(dataset.backgroundColor);
                                        var originalAlpha = dataset._originalBackgroundAlpha;
                                        dataset.backgroundColor = 'rgba(' + bgRgb.r + ',' + bgRgb.g + ',' + bgRgb.b + ',' + (originalAlpha * 0.3) + ')';
                                    }

                                    // Dim point colors as well
                                    if (dataset.pointBackgroundColor) {
                                        var ptBgRgb = _extractRGB(dataset.pointBackgroundColor);
                                        dataset.pointBackgroundColor = 'rgba(' + ptBgRgb.r + ',' + ptBgRgb.g + ',' + ptBgRgb.b + ',0.3)';
                                    }
                                    if (dataset.pointBorderColor) {
                                        var ptBrRgb = _extractRGB(dataset.pointBorderColor);
                                        dataset.pointBorderColor = 'rgba(' + ptBrRgb.r + ',' + ptBrRgb.g + ',' + ptBrRgb.b + ',0.3)';
                                    }
                                    if (dataset.pointHoverBackgroundColor) {
                                        var ptHvBgRgb = _extractRGB(dataset.pointHoverBackgroundColor);
                                        dataset.pointHoverBackgroundColor = 'rgba(' + ptHvBgRgb.r + ',' + ptHvBgRgb.g + ',' + ptHvBgRgb.b + ',0.3)';
                                    }
                                    if (dataset.pointHoverBorderColor) {
                                        var ptHvBrRgb = _extractRGB(dataset.pointHoverBorderColor);
                                        dataset.pointHoverBorderColor = 'rgba(' + ptHvBrRgb.r + ',' + ptHvBrRgb.g + ',' + ptHvBrRgb.b + ',0.3)';
                                    }
                                }
                            });

                            chart.update('none');
                            el.style.cursor = 'pointer';
                        },
                        onLeave: function (evt, legendItem, legend) {
                            // Restore original line opacity
                            var chart = legend.chart;

                            chart.data.datasets.forEach(function (dataset) {
                                // Restore original colors
                                var bc = dataset.borderColor;
                                if (bc && bc.includes('0.3)')) {
                                    var rgb = _extractRGB(bc);
                                    dataset.borderColor = 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',1.0)';
                                }

                                if (dataset.backgroundColor && dataset.backgroundColor !== 'transparent' && dataset.backgroundColor.includes('rgba')) {
                                    var bgRgb = _extractRGB(dataset.backgroundColor);
                                    var originalAlpha = dataset._originalBackgroundAlpha || 0.1;
                                    dataset.backgroundColor = 'rgba(' + bgRgb.r + ',' + bgRgb.g + ',' + bgRgb.b + ',' + originalAlpha + ')';
                                }

                                // Restore point colors
                                if (dataset.pointBackgroundColor && typeof dataset.pointBackgroundColor === 'string' && dataset.pointBackgroundColor.includes('0.3)')) {
                                    var ptBgRgb = _extractRGB(dataset.pointBackgroundColor);
                                    dataset.pointBackgroundColor = 'rgba(' + ptBgRgb.r + ',' + ptBgRgb.g + ',' + ptBgRgb.b + ',1.0)';
                                }
                                if (dataset.pointBorderColor && typeof dataset.pointBorderColor === 'string' && dataset.pointBorderColor.includes('0.3)')) {
                                    var ptBrRgb = _extractRGB(dataset.pointBorderColor);
                                    dataset.pointBorderColor = 'rgba(' + ptBrRgb.r + ',' + ptBrRgb.g + ',' + ptBrRgb.b + ',1.0)';
                                }
                                if (dataset.pointHoverBackgroundColor && typeof dataset.pointHoverBackgroundColor === 'string' && dataset.pointHoverBackgroundColor.includes('0.3)')) {
                                    var ptHvBgRgb = _extractRGB(dataset.pointHoverBackgroundColor);
                                    dataset.pointHoverBackgroundColor = 'rgba(' + ptHvBgRgb.r + ',' + ptHvBgRgb.g + ',' + ptHvBgRgb.b + ',1.0)';
                                }
                                if (dataset.pointHoverBorderColor && typeof dataset.pointHoverBorderColor === 'string' && dataset.pointHoverBorderColor.includes('0.3)')) {
                                    var ptHvBrRgb = _extractRGB(dataset.pointHoverBorderColor);
                                    dataset.pointHoverBorderColor = 'rgba(' + ptHvBrRgb.r + ',' + ptHvBrRgb.g + ',' + ptHvBrRgb.b + ',1.0)';
                                }
                            });

                            chart.update('none');
                            el.style.cursor = 'default';
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0,0,0,0.85)',
                        titleColor: '#fff', bodyColor: '#ddd',
                        borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, padding: 10,
                        itemSort: function (a, b) {
                            return (b.parsed.y || 0) - (a.parsed.y || 0);
                        },
                        callbacks: {
                            label: function (ctx) {
                                var v = ctx.parsed.y;
                                return v != null ? ctx.dataset.label + ': ' + v.toFixed(4) : '';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: t.text, font: { size: 10 }, maxRotation: 45, autoSkip: true, maxTicksLimit: 20 },
                        grid:  { color: t.grid }
                    },
                    y: {
                        title: { display: true, text: yLabel, color: t.text, font: { size: 11 } },
                        ticks: { color: t.text, font: { size: 10 } },
                        grid:  { color: t.grid }
                    }
                }
            }
        });
    }

    // ===================================================================
    // Helper to extract RGB values from color string
    // ===================================================================
    function _extractRGB(colorStr) {
        if (!colorStr) return { r: 0, g: 0, b: 0 };

        // Handle rgba format
        if (colorStr.startsWith('rgba')) {
            var match = colorStr.match(/rgba\(([^,]+),([^,]+),([^,]+)/);
            if (match) {
                return { r: parseInt(match[1]), g: parseInt(match[2]), b: parseInt(match[3]) };
            }
        }

        // Handle rgb format
        if (colorStr.startsWith('rgb')) {
            var match = colorStr.match(/rgb\(([^,]+),([^,]+),([^,]+)/);
            if (match) {
                return { r: parseInt(match[1]), g: parseInt(match[2]), b: parseInt(match[3]) };
            }
        }

        // Handle hex format
        if (colorStr.startsWith('#')) {
            var hex = colorStr.substring(1);
            return {
                r: parseInt(hex.substring(0, 2), 16),
                g: parseInt(hex.substring(2, 4), 16),
                b: parseInt(hex.substring(4, 6), 16)
            };
        }

        return { r: 0, g: 0, b: 0 };
    }

    // ===================================================================
    // Empty canvas message
    // ===================================================================
    function _emptyCanvas(canvasId, msg) {
        var el = document.getElementById(canvasId);
        if (!el) return;

        for (var k in _charts) {
            if (_charts[k] && _charts[k].canvas === el) {
                _charts[k].destroy();
                _charts[k] = null;
                break;
            }
        }

        var ctx = el.getContext('2d');
        ctx.clearRect(0, 0, el.width, el.height);
        var t = _theme();
        ctx.font      = '14px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        ctx.fillStyle = t.text;
        ctx.textAlign = 'center';
        ctx.fillText(msg || 'No data available', el.width / 2, el.height / 2);
    }

    // ===================================================================
    // Fetch intraday refresh logs
    // ===================================================================
    function _fetchIntraday() {
        if (!_s.intradayDate) return;

        console.log('[ERT Intraday] Fetching data for date:', _s.intradayDate, 'timezone:', _s.intradayTimezone);

        var params = new URLSearchParams({
            date: _s.intradayDate,
            limit_runs: _s.intradayLimit
        });

        fetch('/api/exchange-rate/intraday-logs?' + params)
            .then(function (res) {
                if (!res.ok) {
                    return res.json().catch(function () { return {}; }).then(function (j) {
                        throw new Error(j.error || 'Server error ' + res.status);
                    });
                }
                return res.json();
            })
            .then(function (data) {
                console.log('[ERT Intraday] Received', data.runs ? data.runs.length : 0, 'runs');
                _renderIntraday(data.runs || []);
            })
            .catch(function (err) {
                console.error('Intraday fetch error:', err);
                _emptyCanvas('ertIntradayChart', 'Failed to load intraday data: ' + err.message);
            });
    }

    // ===================================================================
    // Render intraday chart (buy rate per bank per run)
    // ===================================================================
    function _renderIntraday(runs) {
        if (!runs.length) {
            _emptyCanvas('ertIntradayChart', 'No intraday refresh data available for this date');
            return;
        }

        console.log('[ERT Intraday] Rendering chart with timezone:', _s.intradayTimezone);

        // Reverse to show oldest first (chronological order)
        runs = runs.slice().reverse();

        // Extract labels (timestamps) and prepare datasets per bank
        var labels = runs.map(function (run, idx) {
            // Parse timestamp from UTC
            var timestamp = run.timestamp;
            var dt = new Date(timestamp); // JavaScript automatically parses ISO 8601 format

            // Convert to selected timezone with 12-hour format
            var timeStr = dt.toLocaleTimeString('en-US', {
                hour: 'numeric',
                minute: '2-digit',
                hour12: true,
                timeZone: _s.intradayTimezone
            });

            // Log first and last timestamp conversions for debugging
            if (idx === 0 || idx === runs.length - 1) {
                console.log('[ERT Intraday] Timestamp', idx + ':', timestamp, '→ UTC Date:', dt.toISOString(), '→', timeStr, 'in', _s.intradayTimezone);
            }

            return timeStr;
        });

        var bankNames = ['CBSL', 'HNB', 'PB', 'SAMPATH'];
        var datasets = bankNames.map(function (bank) {
            var data = runs.map(function (run) {
                var bankData = run.banks[bank];
                if (!bankData || bankData.status !== 'success' || !bankData.buy_rate) {
                    return null; // Missing or failed data
                }
                return bankData.buy_rate;
            });

            return {
                label: bank,
                data: data,
                borderColor: SRC_CLR[bank] || '#6c757d',
                backgroundColor: 'transparent',
                borderWidth: 2,
                fill: false,
                tension: 0.3,
                pointRadius: 3,
                pointHoverRadius: 5,
                spanGaps: true // Connect lines even when data is missing
            };
        });

        // Update info text to show selected timezone
        var infoEl = document.getElementById('ertIntradayInfo');
        if (infoEl) {
            var tzDisplay = _s.intradayTimezone === 'Asia/Colombo' ? 'Sri Lanka (IST)' :
                           _s.intradayTimezone === 'UTC' ? 'UTC' : _s.intradayTimezone;
            infoEl.innerHTML = '<i class="fas fa-info-circle me-1"></i>' +
                'Shows exchange rate refresh attempts throughout the day. Each refresh cycle (run) fetches rates from multiple banks. ' +
                '<strong>Times shown in: ' + tzDisplay + ' (12-hour format, DST-aware)</strong>';
        }

        _lineChart('ertIntradayChart', 'intraday', labels, datasets, 'Buy Rate (LKR)');
    }

    // ===================================================================
    // AI Insights Modal
    // ===================================================================
    function _showAiInsights() {
        // Show modal
        var modal = document.getElementById('aiInsightsModal');
        if (!modal) {
            console.error('AI Insights modal not found');
            return;
        }

        var bsModal = bootstrap.Modal.getOrCreateInstance(modal);
        bsModal.show();

        // Show loading state
        _show('aiInsightsLoading', true);
        _show('aiInsightsError', false);
        _show('aiInsightsData', false);

        // Use comparison months setting for analysis (default 3 months)
        var analysisMonths = _s.compMonths || 3;

        var bankSelect = document.getElementById('aiUserBankSelect');
        var userBank = bankSelect ? bankSelect.value : 'HNB';

        var params = new URLSearchParams({
            months: analysisMonths,
            currency_from: 'USD',
            currency_to: 'LKR',
            user_bank: userBank
        });

        console.log('🔍 Requesting AI insights with params:', {
            months: analysisMonths,
            currency_from: 'USD',
            currency_to: 'LKR',
            user_bank: userBank
        });
        console.log('ℹ️  Backend will fetch CBSL, PB, HNB, SAMPATH data from YOUR database');

        fetch('/api/exchange-rate/ai-insights?' + params)
            .then(function (res) {
                if (!res.ok) {
                    return res.json().catch(function () { return {}; }).then(function (j) {
                        throw new Error(j.message || j.error || 'Server error ' + res.status);
                    });
                }
                return res.json();
            })
            .then(function (data) {
                console.log('✅ AI Insights received (using YOUR database data):', data);

                // Log bank data if available
                if (data.statistics && data.statistics.banks) {
                    var ub = data.statistics.user_bank || userBank;
                    console.log('📊 Bank data from YOUR database:');
                    console.log('  - ' + ub + ' (your bank):', data.statistics.banks[ub]);
                    Object.keys(data.statistics.banks).forEach(function (b) {
                        if (b !== ub) console.log('  - ' + b + ':', data.statistics.banks[b]);
                    });
                }

                _renderAiInsights(data);
            })
            .catch(function (err) {
                console.error('AI Insights error:', err);
                _show('aiInsightsLoading', false);
                _show('aiInsightsError', true);
                var errMsgEl = document.getElementById('aiInsightsErrorMsg');
                if (errMsgEl) {
                    errMsgEl.textContent = err.message || 'Failed to generate AI insights. Please try again.';
                }
            });
    }

    function _renderAiInsights(data) {
        // Hide loading, show content
        _show('aiInsightsLoading', false);
        _show('aiInsightsError', false);
        _show('aiInsightsData', true);

        // Recommendation
        var reco = document.getElementById('aiRecommendation');
        if (reco) {
            reco.textContent = data.recommendation || 'No recommendation available';
        }

        // Confidence badge
        var confBadge = document.getElementById('aiConfidenceBadge');
        if (confBadge && data.confidence) {
            var confClass = data.confidence === 'HIGH' ? 'bg-success' :
                           data.confidence === 'MEDIUM' ? 'bg-warning' : 'bg-secondary';
            confBadge.className = 'badge ' + confClass;
            confBadge.textContent = 'Confidence: ' + data.confidence;
        }

        // Risk badge
        var riskBadge = document.getElementById('aiRiskBadge');
        if (riskBadge && data.risk_level) {
            var riskClass = data.risk_level === 'LOW' ? 'bg-success' :
                           data.risk_level === 'MEDIUM' ? 'bg-warning' : 'bg-danger';
            riskBadge.className = 'badge ' + riskClass;
            riskBadge.textContent = 'Risk: ' + data.risk_level;
        }

        // Statistics - Multi-bank data
        var stats = data.statistics || {};
        var banks = stats.banks || {};
        var userBank = stats.user_bank || 'HNB';

        // Update all dynamic bank name labels
        document.querySelectorAll('.aiFcBankLabel').forEach(function (el) {
            el.textContent = userBank;
        });

        // Show user's bank statistics
        if (banks[userBank]) {
            var ubStats = banks[userBank];
            _txt('aiCurrentRate', ubStats.current ? ubStats.current.toFixed(4) + ' LKR (' + userBank + ')' : '--');
            _txt('aiAvgRate', ubStats.avg ? ubStats.avg.toFixed(4) + ' LKR' : '--');
            _txt('aiRateRange', (ubStats.min && ubStats.max) ?
                ubStats.min.toFixed(4) + ' - ' + ubStats.max.toFixed(4) : '--');

            // Calculate volatility for display
            var volatility = ubStats.max && ubStats.min ?
                ((ubStats.max - ubStats.min) / ubStats.avg * 100).toFixed(2) + '%' : '--';
            _txt('aiVolatility', volatility);
        }

        // User bank position (from multi-bank analysis)
        if (data.hnb_position) {
            var trend = document.getElementById('aiTrend');
            if (trend) {
                trend.innerHTML = '<strong>' + userBank + ' Position:</strong> ' + data.hnb_position + '<br><br>' +
                                 (data.trend || 'No trend analysis available');
            }
        } else {
            // Fallback for old single-bank format
            var trend = document.getElementById('aiTrend');
            if (trend) {
                trend.textContent = data.trend || 'No trend analysis available';
            }
        }

        // Bank Comparison (new field)
        if (data.bank_comparison) {
            var bestTime = document.getElementById('aiBestTime');
            if (bestTime) {
                var html = (data.best_time || 'No specific recommendation') +
                           '<br><br><strong>Bank Comparison:</strong> ' + data.bank_comparison;
                if (data.rate_advantage) {
                    html += '<br><br><strong>💰 Rate Advantage ($1000):</strong> ' + data.rate_advantage;
                }
                bestTime.innerHTML = html;
            }
        } else {
            // Fallback for old format
            var bestTime = document.getElementById('aiBestTime');
            if (bestTime) {
                bestTime.textContent = data.best_time || 'No specific recommendation';
            }
        }

        // Insights list
        var insightsList = document.getElementById('aiInsightsList');
        if (insightsList && data.insights) {
            insightsList.innerHTML = '';
            var insights = Array.isArray(data.insights) ? data.insights : [data.insights];
            insights.forEach(function (insight) {
                var li = document.createElement('li');
                li.textContent = insight;
                li.className = 'mb-1';
                insightsList.appendChild(li);
            });
        }

        // Forecast
        var fcText = document.getElementById('aiForecastText');
        var fcDetail = document.getElementById('aiForecastDetail');
        if (fcText && data.forecast) {
            if (typeof data.forecast === 'string') {
                // Legacy string format
                fcText.textContent = data.forecast;
                if (fcDetail) fcDetail.style.display = 'none';
            } else if (typeof data.forecast === 'object') {
                // Structured forecast object
                var fc = data.forecast;

                // 7-day and 14-day predicted rates
                var fc7d = document.getElementById('aiFc7d');
                var fc14d = document.getElementById('aiFc14d');
                if (fc7d) fc7d.textContent = fc.hnb_7_day || '--';
                if (fc14d) fc14d.textContent = fc.hnb_14_day || '--';

                // Direction badge
                var dirEl = document.getElementById('aiFcDirection');
                if (dirEl && fc.direction) {
                    dirEl.textContent = fc.direction;
                    dirEl.className = 'badge ms-1 ' +
                        (fc.direction === 'RISING' ? 'bg-success' :
                         fc.direction === 'FALLING' ? 'bg-danger' : 'bg-warning text-dark');
                }

                // Confidence
                var confEl = document.getElementById('aiFcConfidence');
                if (confEl && fc.confidence_in_forecast) {
                    confEl.textContent = fc.confidence_in_forecast + ' confidence';
                }

                // Should wait
                var swDiv = document.getElementById('aiFcShouldWait');
                var swText = document.getElementById('aiFcShouldWaitText');
                if (swDiv && swText && fc.should_wait) {
                    swDiv.style.display = 'block';
                    swText.textContent = fc.should_wait;
                }

                // Optimal window
                var owDiv = document.getElementById('aiFcOptimalWindow');
                var owText = document.getElementById('aiFcOptimalWindowText');
                if (owDiv && owText && fc.optimal_window) {
                    owDiv.style.display = 'block';
                    owText.textContent = fc.optimal_window;
                }

                // All banks 7-day predicted
                var brDiv = document.getElementById('aiFcBankRates');
                var brList = document.getElementById('aiFcBankRatesList');
                if (brDiv && brList && fc.all_banks_7d) {
                    brDiv.style.display = 'block';
                    brList.innerHTML = '';
                    var bestBank = fc.best_bank_7d || '';
                    Object.keys(fc.all_banks_7d).forEach(function (bank) {
                        var li = document.createElement('li');
                        var isBest = (bank === bestBank);
                        li.innerHTML = '<strong>' + bank + ':</strong> ' + fc.all_banks_7d[bank] +
                            (isBest ? ' <span class="badge bg-success">Best</span>' : '');
                        brList.appendChild(li);
                    });
                }

                // Summary text (empty if detailed view shown)
                fcText.textContent = '';
                if (fcDetail) fcDetail.style.display = 'block';
            }
        } else if (fcText) {
            fcText.textContent = 'No forecast available';
            if (fcDetail) fcDetail.style.display = 'none';
        }

        // Action items
        var actionsList = document.getElementById('aiActionItemsList');
        if (actionsList && data.action_items) {
            actionsList.innerHTML = '';
            var actions = Array.isArray(data.action_items) ? data.action_items : [data.action_items];
            actions.forEach(function (action) {
                var li = document.createElement('li');
                li.textContent = action;
                li.className = 'mb-1';
                actionsList.appendChild(li);
            });
        }

        // Global Insights
        var globalCard = document.getElementById('aiGlobalInsightsCard');
        var globalContent = document.getElementById('aiGlobalInsightsContent');
        if (globalCard && globalContent && data.global_insights) {
            globalCard.style.display = 'block';
            var gi = data.global_insights;
            var labels = {
                usd_strength: { icon: '💵', title: 'USD Strength' },
                fed_policy_impact: { icon: '🏦', title: 'Fed Policy Impact' },
                commodity_pressure: { icon: '🛢️', title: 'Commodity Pressure' },
                imf_program: { icon: '🌐', title: 'IMF Program' },
                regional_context: { icon: '🌏', title: 'Regional Context' },
                risk_sentiment: { icon: '📊', title: 'Risk Sentiment' },
                key_global_driver: { icon: '🔑', title: 'Key Global Driver' },
                outlook: { icon: '🔮', title: 'Global Outlook' }
            };
            var html = '<dl class="mb-0">';
            Object.keys(labels).forEach(function (key) {
                if (gi[key]) {
                    var l = labels[key];
                    html += '<dt class="mt-2">' + l.icon + ' ' + l.title + '</dt>';
                    html += '<dd class="mb-1 ms-3 small">' + gi[key] + '</dd>';
                }
            });
            html += '</dl>';
            globalContent.innerHTML = html;
        } else if (globalCard) {
            globalCard.style.display = 'none';
        }

        // Metadata
        var stats = data.statistics || {};
        var banks = stats.banks || {};
        var userBank = stats.user_bank || 'HNB';

        if (banks[userBank] && banks[userBank].count) {
            _txt('aiDataPoints', banks[userBank].count + ' (' + userBank + ')');
            if (banks[userBank].first_date && banks[userBank].last_date) {
                _txt('aiDataPeriod', banks[userBank].first_date + ' to ' + banks[userBank].last_date);
            }
        } else {
            _txt('aiDataPoints', stats.data_points || '--');
            _txt('aiDataPeriod', stats.period || '--');
        }

        var genAt = document.getElementById('aiGeneratedAt');
        if (genAt && data.generated_at) {
            var date = new Date(data.generated_at);
            genAt.textContent = date.toLocaleString();
        }
    }

    // ===================================================================
    // Salary Calculator Modal
    // ===================================================================
    var _salaryCalc = {
        exchanges: [],
        currentRates: null,
        nextExchangeId: 1,
        currentEditId: null  // Track if we're editing an existing calculation
    };

    function _showSalaryCalculator() {
        var modal = document.getElementById('salaryCalcModal');
        if (!modal) {
            console.error('Salary Calculator modal not found');
            return;
        }

        var bsModal = bootstrap.Modal.getOrCreateInstance(modal);
        bsModal.show();

        // Reset calculator state
        _salaryCalc.exchanges = [];
        _salaryCalc.nextExchangeId = 1;
        _salaryCalc.currentEditId = null;
        document.getElementById('salaryTotalUSD').value = '';
        document.getElementById('salaryNotes').value = '';
        document.getElementById('exchangeEntries').innerHTML = '';
        _updateSalarySummary();
        _updateSaveButtonText();

        // Bind buttons
        var addExchangeBtn = document.getElementById('addExchangeBtn');
        if (addExchangeBtn) {
            addExchangeBtn.onclick = _addExchangeEntry;
        }

        var saveCalcBtn = document.getElementById('saveCalcBtn');
        if (saveCalcBtn) {
            saveCalcBtn.onclick = _saveSalaryCalculation;
        }

        // Fetch current bank rates
        _fetchCurrentBankRates();

        // Load calculation history
        _loadSalaryHistory();

        // Add initial exchange entry
        _addExchangeEntry();
    }

    function _fetchCurrentBankRates() {
        fetch('/api/salary-calc/current-rates')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                _salaryCalc.currentRates = data.rates || {};
                console.log('Current bank rates loaded:', _salaryCalc.currentRates);
            })
            .catch(function (err) {
                console.error('Error fetching current rates:', err);
            });
    }

    function _addExchangeEntry() {
        var exchangeId = _salaryCalc.nextExchangeId++;
        var container = document.getElementById('exchangeEntries');

        var entryDiv = document.createElement('div');
        entryDiv.className = 'card mb-2';
        entryDiv.id = 'exchange-' + exchangeId;
        entryDiv.setAttribute('data-exchange-id', exchangeId);

        var rateOptions = _buildRateOptions();

        var removeBtn = exchangeId > 1
            ? '<button type="button" class="btn btn-sm btn-outline-danger d-inline-flex align-items-center" onclick="window._removeExchange(' + exchangeId + ')">\                        <i class="fas fa-times"></i>\                    </button>'
            : '';

        entryDiv.innerHTML = '\
            <div class="card-body p-2">\
                <div class="d-flex justify-content-between align-items-center mb-2">\
                    <strong class="small">Exchange #' + exchangeId + '</strong>\
                    ' + removeBtn + '\
                </div>\
                <div class="row g-2">\
                    <div class="col-6">\
                        <label class="form-label small mb-1">USD Amount</label>\
                        <div class="input-group input-group-sm">\
                            <span class="input-group-text">$</span>\
                            <input type="number" class="form-control exchange-usd" data-id="' + exchangeId + '" \
                                   placeholder="0.00" step="0.01" min="0">\
                        </div>\
                    </div>\
                    <div class="col-6">\
                        <label class="form-label small mb-1">LKR Rate</label>\
                        <select class="form-select form-select-sm exchange-rate-select" data-id="' + exchangeId + '">\
                            <option value="">Select Bank or Manual</option>\
                            <optgroup label="Current Bank Rates">\
                                ' + rateOptions + '\
                            </optgroup>\
                            <option value="manual">Manual Entry</option>\
                        </select>\
                        <input type="number" class="form-control form-control-sm mt-1 exchange-rate-manual" \
                               data-id="' + exchangeId + '" placeholder="Enter rate" step="0.0001" min="0" style="display:none;">\
                    </div>\
                </div>\
            </div>\
        ';

        container.appendChild(entryDiv);

        // Bind events
        var usdInput = entryDiv.querySelector('.exchange-usd');
        var rateSelect = entryDiv.querySelector('.exchange-rate-select');
        var rateManual = entryDiv.querySelector('.exchange-rate-manual');

        usdInput.addEventListener('input', _updateSalarySummary);
        rateSelect.addEventListener('change', function () {
            if (this.value === 'manual') {
                rateManual.style.display = 'block';
                rateManual.value = '';
                rateManual.focus();
            } else {
                rateManual.style.display = 'none';
            }
            _updateSalarySummary();
        });
        rateManual.addEventListener('input', _updateSalarySummary);
    }

    window._removeExchange = function(exchangeId) {
        // Prevent removing the first exchange entry
        if (exchangeId === 1) {
            showToast('The first exchange entry cannot be removed', 'warning');
            return;
        }
        var entry = document.getElementById('exchange-' + exchangeId);
        if (entry) {
            entry.remove();
            _updateSalarySummary();
        }
    };

    function _buildRateOptions() {
        if (!_salaryCalc.currentRates) return '';

        var options = '';
        var banks = ['HNB', 'PB', 'SAMPATH'];
        banks.forEach(function (bank) {
            var rate = _salaryCalc.currentRates[bank];
            if (rate && rate.buy_rate) {
                options += '<option value="' + bank + '|' + rate.buy_rate + '">' +
                          bank + ': ' + rate.buy_rate.toFixed(4) + ' රු</option>';
            }
        });
        return options;
    }

    function _updateSalarySummary() {
        var totalUSD = parseFloat(document.getElementById('salaryTotalUSD').value) || 0;
        var entries = document.querySelectorAll('[data-exchange-id]');

        var totalExchangedUSD = 0;
        var totalLKR = 0;

        entries.forEach(function (entry) {
            var id = entry.getAttribute('data-exchange-id');
            var usdInput = entry.querySelector('.exchange-usd');
            var rateSelect = entry.querySelector('.exchange-rate-select');
            var rateManual = entry.querySelector('.exchange-rate-manual');

            var usd = parseFloat(usdInput.value) || 0;
            var rate = 0;

            if (rateSelect.value && rateSelect.value !== 'manual') {
                // Format: "BANK|rate"
                var parts = rateSelect.value.split('|');
                if (parts.length === 2) {
                    rate = parseFloat(parts[1]);
                }
            } else if (rateSelect.value === 'manual' && rateManual.value) {
                rate = parseFloat(rateManual.value) || 0;
            }

            if (usd > 0 && rate > 0) {
                totalExchangedUSD += usd;
                totalLKR += usd * rate;
            }
        });

        var remainingUSD = totalUSD - totalExchangedUSD;
        var avgRate = totalExchangedUSD > 0 ? totalLKR / totalExchangedUSD : 0;

        // Update summary
        document.getElementById('summaryTotalUSD').textContent = '$' + totalUSD.toFixed(2);
        document.getElementById('summaryTotalLKR').textContent = 'රු ' + totalLKR.toFixed(2);
        document.getElementById('summaryRemainingUSD').textContent = '$' + remainingUSD.toFixed(2);
        document.getElementById('summaryAvgRate').textContent = avgRate.toFixed(4);

        // Show warning if amounts don't match
        var warningMsg = document.getElementById('warningMsg');
        var warningText = document.getElementById('warningText');
        if (totalUSD > 0 && Math.abs(remainingUSD) > 0.01) {
            warningMsg.style.display = 'block';
            if (remainingUSD > 0) {
                warningText.textContent = 'You have $' + remainingUSD.toFixed(2) + ' USD remaining (partial save allowed)';
                warningMsg.className = 'mt-2';
                warningText.className = 'text-warning';
                warningText.innerHTML = '<i class="fas fa-info-circle me-1"></i>' + warningText.textContent;
            } else {
                warningText.textContent = 'Total exchanges exceed salary by $' + Math.abs(remainingUSD).toFixed(2);
                warningMsg.className = 'mt-2';
                warningText.className = 'text-danger';
                warningText.innerHTML = '<i class="fas fa-exclamation-triangle me-1"></i>' + warningText.textContent;
            }
        } else {
            warningMsg.style.display = 'none';
        }
    }

    function _updateSaveButtonText() {
        var saveBtn = document.getElementById('saveCalcBtn');
        if (saveBtn) {
            if (_salaryCalc.currentEditId) {
                saveBtn.innerHTML = '<i class="fas fa-edit me-1"></i>Update Calculation';
            } else {
                saveBtn.innerHTML = '<i class="fas fa-save me-1"></i>Save Calculation';
            }
        }
    }

    function _saveSalaryCalculation() {
        var totalUSD = parseFloat(document.getElementById('salaryTotalUSD').value) || 0;
        var notes = document.getElementById('salaryNotes').value.trim();

        if (totalUSD <= 0) {
            showToast('Please enter a valid total USD salary amount', 'warning');
            return;
        }

        // Collect exchanges
        var exchanges = [];
        var entries = document.querySelectorAll('[data-exchange-id]');

        entries.forEach(function (entry) {
            var usdInput = entry.querySelector('.exchange-usd');
            var rateSelect = entry.querySelector('.exchange-rate-select');
            var rateManual = entry.querySelector('.exchange-rate-manual');

            var usd = parseFloat(usdInput.value) || 0;
            var rate = 0;
            var bank = null;

            if (rateSelect.value && rateSelect.value !== 'manual') {
                var parts = rateSelect.value.split('|');
                if (parts.length === 2) {
                    bank = parts[0];
                    rate = parseFloat(parts[1]);
                }
            } else if (rateSelect.value === 'manual' && rateManual.value) {
                rate = parseFloat(rateManual.value) || 0;
                bank = 'Manual';
            }

            if (usd > 0 && rate > 0) {
                exchanges.push({
                    usd_amount: usd,
                    exchange_rate: rate,
                    bank_source: bank
                });
            }
        });

        if (exchanges.length === 0) {
            showToast('Please add at least one exchange entry with valid USD amount and rate', 'warning');
            return;
        }

        // Check total doesn't exceed salary
        var totalExchanged = exchanges.reduce(function (sum, ex) { return sum + ex.usd_amount; }, 0);
        if (totalExchanged > totalUSD) {
            showToast('Total exchanged USD ($' + totalExchanged.toFixed(2) + ') exceeds total salary ($' + totalUSD.toFixed(2) + ')', 'danger');
            return;
        }

        // Save to backend
        var saveBtn = document.getElementById('saveCalcBtn');
        saveBtn.disabled = true;
        var isUpdate = _salaryCalc.currentEditId !== null;
        saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>' + (isUpdate ? 'Updating...' : 'Saving...');

        var requestData = {
            total_usd: totalUSD,
            exchanges: exchanges,
            notes: notes
        };

        if (isUpdate) {
            requestData.calculation_id = _salaryCalc.currentEditId;
        }

        var url = isUpdate ? '/api/salary-calc/update' : '/api/salary-calc/create';
        var method = isUpdate ? 'PUT' : 'POST';

        fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestData)
        })
        .then(function (res) {
            if (!res.ok) throw new Error('Failed to save calculation');
            return res.json();
        })
        .then(function (data) {
            console.log('Salary calculation saved:', data);
            var msg = isUpdate ? 'Calculation updated successfully!' : 'Calculation saved successfully!';
            var details = 'Total: $' + data.total_usd + ' → රු ' + data.total_lkr.toFixed(2);
            if (data.is_partial) {
                details += ' (Partial - $' + data.total_exchanged_usd.toFixed(2) + ' of $' + data.total_usd.toFixed(2) + ' exchanged)';
            }
            details += ' • Avg Rate: ' + data.average_rate.toFixed(4);
            showToast(msg + ' — ' + details, 'success');

            // Reset form
            document.getElementById('salaryTotalUSD').value = '';
            document.getElementById('salaryNotes').value = '';
            document.getElementById('exchangeEntries').innerHTML = '';
            _salaryCalc.exchanges = [];
            _salaryCalc.nextExchangeId = 1;
            _salaryCalc.currentEditId = null;
            _updateSalarySummary();
            _updateSaveButtonText();
            _addExchangeEntry();

            // Reload history
            _loadSalaryHistory();
        })
        .catch(function (err) {
            console.error('Error saving calculation:', err);
            showToast('Failed to save calculation: ' + err.message, 'danger');
        })
        .finally(function () {
            saveBtn.disabled = false;
            _updateSaveButtonText();
        });
    }

    window._editSalaryCalc = function(calcId) {
        // Load calculation into the form for editing
        fetch('/api/salary-calc/history')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                var calc = data.calculations.find(function (c) { return c.id === calcId; });
                if (!calc) {
                    showToast('Calculation not found', 'danger');
                    return;
                }

                // Set edit mode
                _salaryCalc.currentEditId = calcId;

                // Populate form
                document.getElementById('salaryTotalUSD').value = calc.total_usd;
                document.getElementById('salaryNotes').value = calc.notes || '';
                document.getElementById('exchangeEntries').innerHTML = '';
                _salaryCalc.nextExchangeId = 1;

                // Add exchanges
                calc.exchanges.forEach(function (ex) {
                    _addExchangeEntry();
                    var lastEntry = document.querySelector('[data-exchange-id]:last-child');
                    if (!lastEntry) {
                        var entries = document.querySelectorAll('[data-exchange-id]');
                        lastEntry = entries[entries.length - 1];
                    }

                    if (lastEntry) {
                        var usdInput = lastEntry.querySelector('.exchange-usd');
                        var rateSelect = lastEntry.querySelector('.exchange-rate-select');
                        var rateManual = lastEntry.querySelector('.exchange-rate-manual');

                        usdInput.value = ex.usd_amount;

                        // Try to match with current bank rates
                        var matched = false;
                        if (ex.bank_source && ex.bank_source !== 'Manual') {
                            var option = rateSelect.querySelector('option[value="' + ex.bank_source + '|' + ex.exchange_rate + '"]');
                            if (option) {
                                rateSelect.value = option.value;
                                matched = true;
                            }
                        }

                        if (!matched) {
                            rateSelect.value = 'manual';
                            rateManual.style.display = 'block';
                            rateManual.value = ex.exchange_rate;
                        }
                    }
                });

                _updateSalarySummary();
                _updateSaveButtonText();

                // Scroll to top of modal
                var modalBody = document.querySelector('#salaryCalcModal .modal-body');
                if (modalBody) modalBody.scrollTop = 0;
            })
            .catch(function (err) {
                console.error('Error loading calculation:', err);
                showToast('Failed to load calculation', 'danger');
            });
    };

    window._deleteSalaryCalc = function(calcId) {
        showConfirmModal(
            'Delete Calculation',
            'Are you sure you want to delete this salary calculation? This action cannot be undone.',
            function() {
                fetch('/api/salary-calc/delete?calculation_id=' + calcId, {
                    method: 'DELETE'
                })
                .then(function (res) {
                    if (!res.ok) throw new Error('Failed to delete');
                    return res.json();
                })
                .then(function () {
                    showToast('Calculation deleted successfully', 'success');
                    _loadSalaryHistory();
                })
                .catch(function (err) {
                    console.error('Error deleting calculation:', err);
                    showToast('Failed to delete calculation', 'danger');
                });
            },
            'Delete',
            'btn-danger'
        );
    };

    function _loadSalaryHistory() {
        var loadingEl = document.getElementById('salaryHistoryLoading');
        var emptyEl = document.getElementById('salaryHistoryEmpty');
        var listEl = document.getElementById('salaryHistoryList');

        loadingEl.style.display = 'block';
        emptyEl.style.display = 'none';
        listEl.style.display = 'none';

        fetch('/api/salary-calc/history')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                loadingEl.style.display = 'none';

                if (!data.calculations || data.calculations.length === 0) {
                    emptyEl.style.display = 'block';
                    return;
                }

                listEl.style.display = 'block';
                listEl.innerHTML = '';

                data.calculations.forEach(function (calc) {
                    var card = document.createElement('div');
                    card.className = 'card mb-2';

                    var calcDate = new Date(calc.calculation_date).toLocaleDateString();
                    var createdDate = new Date(calc.created_at).toLocaleString();

                    // Calculate if this is a partial calculation
                    var totalExchanged = calc.exchanges.reduce(function (sum, ex) { return sum + parseFloat(ex.usd_amount); }, 0);
                    var isPartial = totalExchanged < parseFloat(calc.total_usd);
                    var partialBadge = isPartial ? '<span class="badge bg-warning text-dark ms-2 d-inline-flex align-items-center" style="height: fit-content;">Partial</span>' : '';

                    var exchangesHtml = '';
                    calc.exchanges.forEach(function (ex, idx) {
                        var bankLabel = ex.bank_source || 'Unknown';
                        exchangesHtml += '<li class="small">$' + ex.usd_amount.toFixed(2) +
                                       ' @ ' + ex.exchange_rate.toFixed(4) +
                                       ' (' + bankLabel + ') = රු ' + ex.lkr_amount.toFixed(2) + '</li>';
                    });

                    card.innerHTML = '\
                        <div class="card-body p-2">\
                            <div class="d-flex justify-content-between align-items-start mb-1">\
                                <div>\
                                    <strong class="text-primary">$' + calc.total_usd.toFixed(2) + ' → රු ' + calc.total_lkr.toFixed(2) + '</strong>' + partialBadge + '\
                                    <div class="small text-muted">' + calcDate + '</div>\
                                </div>\
                                <div class="d-flex gap-1 align-items-center">\
                                    <span class="badge bg-info d-inline-flex align-items-center" style="height: fit-content;">Avg: ' + calc.average_rate.toFixed(4) + '</span>\
                                    <button class="btn btn-sm btn-outline-primary" onclick="window._editSalaryCalc(' + calc.id + ')" title="Edit">\
                                        <i class="fas fa-edit"></i>\
                                    </button>\
                                    <button class="btn btn-sm btn-outline-danger" onclick="window._deleteSalaryCalc(' + calc.id + ')" title="Delete">\
                                        <i class="fas fa-trash"></i>\
                                    </button>\
                                </div>\
                            </div>\
                            <div class="small mb-2">\
                                <strong>Breakdown:</strong>\
                                <ul class="mb-0 ps-3">' + exchangesHtml + '</ul>\
                            </div>\
                            ' + (calc.notes ? '<div class="small text-muted"><i class="fas fa-note-sticky me-1"></i>' + calc.notes + '</div>' : '') + '\
                            <div class="small text-muted mt-1"><i class="fas fa-clock me-1"></i>Created: ' + createdDate + '</div>\
                        </div>\
                    ';

                    listEl.appendChild(card);
                });
            })
            .catch(function (err) {
                console.error('Error loading history:', err);
                loadingEl.style.display = 'none';
                emptyEl.style.display = 'block';
            });
    }

})();