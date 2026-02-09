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
        months: 6,
        forecastDays: 30,
        forecastHistory: 3,
        compMonths: 3
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
            _bindControls();
            _bound = true;
        }
        _fetchAll();
    };

    // ===================================================================
    // Bind controls (once)
    // ===================================================================
    function _bindControls() {
        var btns = document.querySelectorAll('#ertPeriodSelector .btn');
        btns.forEach(function (btn) {
            btn.addEventListener('click', function () {
                btns.forEach(function (b) { b.classList.remove('active'); });
                btn.classList.add('active');
                _s.period = btn.getAttribute('data-period');
                _fetchAll();
            });
        });

        _on('ertMonthsSelector',  'change', function () { _s.months          = +this.value; _fetchAll(); });
        _on('ertForecastDays',    'change', function () { _s.forecastDays    = +this.value; _fetchAll(); });
        _on('ertForecastHistory', 'change', function () { _s.forecastHistory = +this.value; _fetchAll(); });
        _on('ertCompMonths',      'change', function () { _s.compMonths      = +this.value; _fetchAll(); });
        _on('ertRefreshBtn',      'click',  function () { _cache = null; _fetchAll(); });
    }

    function _on(id, evt, fn) {
        var el = document.getElementById(id);
        if (el) el.addEventListener(evt, fn);
    }

    // ===================================================================
    // Single API fetch
    // ===================================================================
    function _fetchAll() {
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

        // Volatility
        if (last.buy_rate_volatility != null) {
            _txt('ertVolatility', last.buy_rate_volatility.toFixed(4));
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
                        labels: { color: t.text, font: { size: 11 }, usePointStyle: true, pointStyle: 'line' }
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

})();
